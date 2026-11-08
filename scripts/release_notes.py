#!/usr/bin/env python3
"""Print the GitHub release notes for a version, from CHANGELOG.md.

    python3 scripts/release_notes.py 1.5.0

The changelog is the one place the notes are written; the release is made from it, so the two cannot
drift apart.
"""

import pathlib
import re
import sys

REPO = "Emadhabibnia1385/KasbBook"


def main(version: str) -> int:
    text = pathlib.Path(__file__).resolve().parents[1].joinpath("CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if match is None:
        print(f"no section for {version} in CHANGELOG.md", file=sys.stderr)
        return 1
    previous = re.findall(r"^## (\S+)", text, re.M)
    older = previous[previous.index(version) + 1] if version in previous and previous.index(version) + 1 < len(previous) else None
    print(f'<p align="center"><img src="https://raw.githubusercontent.com/{REPO}/main/assets/readme/social-preview.png" alt="KasbBook {version}" width="100%"></p>\n')
    print("Docs: <https://emadhabibnia1385.github.io/KasbBook/> · [فارسی](https://emadhabibnia1385.github.io/KasbBook/fa/)\n")
    print(match.group(1).strip())
    if older:
        print(f"\n**Full changelog:** https://github.com/{REPO}/compare/v{older}...v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].lstrip("v")))
