"""The public URLs are written down in seven places; they must agree.

The API host moved once already, and it was named in mkdocs.yml, both index
pages, both READMEs and both API pages. Updating six of seven leaves a button
on the site pointing at a host that no longer answers, and nothing fails —
a link is not imported by anything.

This does not check that a URL resolves. CI has no business depending on
somebody's DNS, and a test that fails when a server is down is a test people
learn to ignore. It checks only that the repository tells one story.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]

# Where a public URL may legitimately appear. Anything else naming a kasbbook
# host is a copy nobody will remember to update.
FILES = [
    "mkdocs.yml",
    "README.md",
    "README.fa.md",
    ".env.example",
    # The bot links to the guide, so the site's address is compiled in as a
    # default. That is one more copy to keep in step with the rest.
    "src/kasbbook/shared/settings.py",
    *(f"docs/{p.name}" for p in sorted((REPO / "docs").glob("*.md"))),
]

# Hosts a documentation example is allowed to invent.
PLACEHOLDERS = {"kasbbook.example.com", "your.host"}

HOST = re.compile(r"https?://([A-Za-z0-9.-]*kasbbook[A-Za-z0-9.-]*)")


def _hosts() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name in FILES:
        path = REPO / name
        if not path.exists():
            continue
        for host in HOST.findall(path.read_text(encoding="utf-8")):
            if host in PLACEHOLDERS:
                continue
            found.setdefault(host, []).append(name)
    return found


def test_one_public_api_host():
    """Every real kasbbook host in the docs is the same host."""
    hosts = {h: f for h, f in _hosts().items() if "github.io" not in h}
    assert len(hosts) <= 1, (
        "more than one API host is referenced, so at least one of these is "
        f"stale: { {h: sorted(set(f)) for h, f in hosts.items()} }"
    )


def test_the_documentation_site_url_agrees_everywhere():
    """The published site's own address, wherever it is written down."""
    site = re.compile(r"https://[A-Za-z0-9.-]+\.github\.io/[A-Za-z0-9_-]+")
    seen: set[str] = set()
    for name in FILES:
        path = REPO / name
        if path.exists():
            seen.update(site.findall(path.read_text(encoding="utf-8")))
    assert len(seen) <= 1, f"the site is linked under more than one address: {sorted(seen)}"


def test_public_urls_are_https():
    """A link handed to a reader must not downgrade them to plain HTTP."""
    for host, files in _hosts().items():
        for name in set(files):
            text = (REPO / name).read_text(encoding="utf-8")
            assert f"http://{host}" not in text, f"{name} links to {host} over plain HTTP"
