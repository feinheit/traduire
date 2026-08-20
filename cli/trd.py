import sys
import tomllib
from pathlib import Path
from urllib.parse import urljoin

import click
import requests


CLI_API = "1"  # Bump this when changing the API in incompatible ways


def _session(project):
    session = requests.Session()
    session.headers = {
        "x-token": project["token"],
        "x-cli-api": CLI_API,
    }
    return session


@click.group()
@click.version_option(package_name="traduire-cli")
def cli():
    pass


@click.command()
@click.argument("folder", type=click.Path(exists=True))
def get(folder):
    """Fetch all pofiles from the server"""
    project = current_project()
    session = _session(project)
    pofiles = find_pofiles(folder)
    for pofile in pofiles:
        url = url_from_pofile(project, pofile)
        r = session.get(url, timeout=10)
        if r.ok:
            pofile.write_text(r.content.decode("utf-8"))
            click.echo(f"Updated {pofile}")
        else:
            _terminate(r.text)


@click.command()
@click.argument("folder", type=click.Path(exists=True))
def submit(folder):
    """Submit updated pofiles to the server for translation"""
    project = current_project()
    session = _session(project)
    pofiles = find_pofiles(sys.argv[2])
    for pofile in pofiles:
        url = url_from_pofile(project, pofile)
        r = session.post(url, data=pofile.read_bytes())
        if r.ok:
            click.echo(f"Submitted {pofile} to the server for translation")
        else:
            _terminate(r.text)


@click.command()
@click.argument("folder", type=click.Path(exists=True))
def replace(folder):
    """Replace pofiles on the server"""
    project = current_project()
    session = _session(project)
    pofiles = find_pofiles(sys.argv[2])
    for pofile in pofiles:
        url = url_from_pofile(project, pofile)
        r = session.put(url, data=pofile.read_bytes())
        if r.ok:
            click.echo(f"Replaced {pofile} on the server")
        else:
            _terminate(r.text)


cli.add_command(get)
cli.add_command(submit)
cli.add_command(replace)


def _terminate(msg):
    click.echo(msg, file=sys.stderr)
    sys.exit(1)


def current_project():
    config = Path.home() / ".config" / "traduire.toml"
    if not config.exists():
        _terminate(f"Config file {config} doesn't exist.")

    data = tomllib.loads(config.read_text())
    cwd = Path.cwd()

    for project in data.get("project", ()):
        path = Path(project["path"]).expanduser()
        if path == cwd:
            return project

    _terminate(f"Couldn't find a project for the current working directory {cwd}")
    return None


def find_pofiles(root):
    def _generate():
        path = Path(root).resolve()
        for dirpath, _dirnames, filenames in path.walk():
            for filename in filenames:
                if filename.endswith(".po"):
                    yield dirpath / filename

    return list(_generate())


def url_from_pofile(project, pofile):
    return urljoin(
        project["url"],
        f"{pofile.parts[-3]}/{pofile.parts[-1].removesuffix('.po')}/",
    )


if __name__ == "__main__":
    cli()
