import re

import httpx2


class TranslationError(Exception):
    pass


# Matches %(name)s-style and {name} / {0} / {name:spec}-style placeholders
_VARIABLE_RE = re.compile(r"%\(\w+\)\w|\{[^}]+\}")


def _variable_name(placeholder):
    """Extract a human-readable name from a placeholder for DeepL context."""
    # %(count)s → "count"
    m = re.match(r"%\((\w+)\)", placeholder)
    if m:
        return m.group(1)
    # {name}, {0}, {name:.2f} → the part before any colon
    m = re.match(r"\{([^}:]+)", placeholder)
    if m:
        return m.group(1)
    return placeholder


def find_variables(text):
    """Return all placeholder variables found in text."""
    return _VARIABLE_RE.findall(text)


def _protect_variables(text):
    """Replace variables with named <var> tags so DeepL won't translate them.

    The variable name is kept as tag content so translation engines can use it
    as context. An id attribute ensures unambiguous restoration for duplicates.

    Returns (modified_text, list_of_original_placeholders).
    """
    placeholders = []

    def replace(match):
        original = match.group(0)
        name = _variable_name(original)
        idx = len(placeholders)
        placeholders.append(original)
        return f'<var id="{idx}">{name}</var>'

    return _VARIABLE_RE.sub(replace, text), placeholders


def _restore_variables(text, placeholders):
    """Restore <var> tags back to the original placeholders."""
    return re.sub(
        r'<var id="(\d+)">[^<]*</var>',
        lambda m: placeholders[int(m.group(1))],
        text,
    )


async def translate_by_deepl(text, to_language, auth_key):
    # Copied 1:1 from django-rosetta, thanks!
    if auth_key.lower().endswith(":fx"):
        endpoint = "https://api-free.deepl.com"
    else:
        endpoint = "https://api.deepl.com"

    protected, placeholders = _protect_variables(text)

    try:
        async with httpx2.AsyncClient() as client:
            r = await client.post(
                f"{endpoint}/v2/translate",
                headers={"Authorization": f"DeepL-Auth-Key {auth_key}"},
                data={
                    "tag_handling": "xml",
                    "ignore_tags": "var",
                    "target_lang": to_language.upper(),
                    "text": protected,
                },
                timeout=5,
            )
    except httpx2.TimeoutException as exc:
        raise TranslationError(
            "The Deepl request timed out. Please try again later."
        ) from exc

    if r.status_code != 200:
        raise TranslationError(
            f"Deepl response is {r.status_code}. Please check your API key or try again later."
        )
    try:
        translated = r.json().get("translations")[0].get("text")
        return _restore_variables(translated, placeholders)
    except Exception as exc:
        raise TranslationError(
            "Deepl returned a non-JSON or unexpected response."
        ) from exc


def fix_nls(in_, out_):
    # Thanks, django-rosetta!
    """Fixes submitted translations by filtering carriage returns and pairing
    newlines at the begging and end of the translated string with the original
    """
    if len(in_) == 0 or len(out_) == 0:
        return out_

    if "\r" in out_ and "\r" not in in_:
        out_ = out_.replace("\r", "")

    if in_[0] == "\n" and out_[0] != "\n":
        out_ = "\n" + out_
    elif in_[0] != "\n" and out_[0] == "\n":
        out_ = out_.lstrip()
    if len(out_) == 0:
        pass
    elif in_[-1] == "\n" and out_[-1] != "\n":
        out_ = out_ + "\n"
    elif in_[-1] != "\n" and out_[-1] == "\n":
        out_ = out_.rstrip()
    return out_
