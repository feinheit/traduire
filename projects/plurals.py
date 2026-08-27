"""Helpers for gettext plural forms.

PO files number plural translations by *plural form index*, not by item count:
``msgstr[0]`` is the first form of the target language's plural rule -- not
"the translation for zero items". Which counts end up in which form is decided
by the ``Plural-Forms`` header of the catalog, so that's what we use when
labelling fields and when deciding which msgid a form translates.
"""

import gettext
import re

from django.utils.translation import gettext as _


# The gettext default (and by far the most common) rule: form 0 for n == 1.
DEFAULT_PLURAL_FORMS = "nplurals=2; plural=(n != 1);"

_NPLURALS_RE = re.compile(r"nplurals\s*=\s*(\d+)")
_PLURAL_RE = re.compile(r"plural\s*=\s*(.+)")

# How far we look for example counts, and how many we show per form.
_EXAMPLES_UP_TO = 200
_EXAMPLE_COUNT = 3


def parse_plural_forms(plural_forms):
    """Return ``(nplurals, rule)`` for a ``Plural-Forms`` header value.

    Missing headers fall back to the gettext default. ``rule`` maps a count to
    its plural form index, or is ``None`` if the header contains an expression
    ``gettext`` refuses to parse -- catalogs are user-provided, after all.
    """
    header = plural_forms or DEFAULT_PLURAL_FORMS

    match = _NPLURALS_RE.search(header)
    nplurals = max(int(match.group(1)), 1) if match else 2

    rule = None
    if match := _PLURAL_RE.search(header):
        try:
            # c2py handles the C ternaries and rejects anything which isn't a
            # plural expression instead of evaluating it.
            rule = gettext.c2py(match.group(1).strip().rstrip(";"))
        except (ValueError, SyntaxError):
            pass

    return nplurals, rule


def plural_form_index(plural_forms, n):
    """Return the plural form index used for ``n``, or ``None`` if unknown."""
    nplurals, rule = parse_plural_forms(plural_forms)
    if nplurals == 1:
        return 0
    if rule is None:
        return None
    index = rule(n)
    return index if 0 <= index < nplurals else None


def singular_form_index(plural_forms):
    """Return the plural form index the singular ``msgid`` corresponds to.

    That's the form used for ``n == 1``. Languages with a single plural form
    have no singular at all -- the one string has to work for every count --
    so ``None`` is returned and ``msgid_plural`` is the better source there.
    """
    nplurals, _rule = parse_plural_forms(plural_forms)
    return None if nplurals == 1 else plural_form_index(plural_forms, 1)


def source_for_form(entry, index, plural_forms):
    """Return the msgid which ``msgstr[index]`` of ``entry`` translates."""
    if not entry.msgid_plural:
        return entry.msgid
    return (
        entry.msgid
        if index == singular_form_index(plural_forms)
        else entry.msgid_plural
    )


def plural_form_examples(plural_forms):
    """Map each plural form index to example counts using that form."""
    nplurals, rule = parse_plural_forms(plural_forms)
    examples = {index: [] for index in range(nplurals)}
    if rule is None:
        return examples
    for n in range(_EXAMPLES_UP_TO + 1):
        counts = examples.get(rule(n))
        # One more than we show, so that we know whether to truncate.
        if counts is not None and len(counts) <= _EXAMPLE_COUNT:
            counts.append(n)
    return examples


def plural_form_labels(plural_forms, indexes):
    """Return labels for the ``msgstr[index]`` fields of a single entry."""
    examples = plural_form_examples(plural_forms)
    labels = {}
    for index in indexes:
        counts = examples.get(index) or []
        numbers = ", ".join(str(n) for n in counts[:_EXAMPLE_COUNT])
        if len(counts) > _EXAMPLE_COUNT:
            numbers = _("{counts} and so on").format(counts=numbers)
        labels[index] = (
            _("Plural form {index} (n = {counts})").format(index=index, counts=numbers)
            if numbers
            else _("Plural form {index}").format(index=index)
        )
    return labels
