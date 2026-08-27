# AGENTS.md

Traduire is a Django app for editing gettext catalogs, see `README.md` for the
big picture and the development setup (`fl local`, `fl dev`).

## Layout

- `projects/` -- the actual application: catalogs, entry editing form,
  plural form handling, DeepL suggestions, API used by the CLI, feeds.
- `accounts/` -- users, login (email, Google and Microsoft SSO).
- `app/` -- settings, templates, static files.
- `cli/` -- the separately distributed `traduire-cli` package.
- `conf/locale/` -- Traduire's own translations. `.po` **and** `.mo` files are
  committed; run `msgfmt` after editing a `.po` file.

## Tests

    ./runtests.sh                 # everything, with a coverage report
    ./runtests.sh projects        # a single app, module or test

The suite reuses the test database (`--keepdb`) and expects a local PostgreSQL
database without authentication.

## Linting and formatting

Ruff is configured in `pyproject.toml` but isn't installed in the virtualenv:

    uvx ruff format .
    uvx ruff check .

JavaScript and CSS in `frontend/` use Biome (`biome.json`).

## Conventions

- Commit feature by feature: one commit per self-contained change, including
  its tests and translation updates. Don't lump unrelated changes together.
- No attribution in commit messages: no `Co-Authored-By` trailers, no
  "Generated with ..." lines.
- The catalogs in `conf/locale/` are maintained with file-granular location
  comments (`#: projects/forms.py`, no line numbers). Editing the affected
  entries by hand keeps diffs small; if you do run `makemessages`, use
  `--add-location file`.
- User-facing strings are translated (`gettext`), and translations for `de`
  and `fr` are added along with the change; `it` is mostly untranslated.
