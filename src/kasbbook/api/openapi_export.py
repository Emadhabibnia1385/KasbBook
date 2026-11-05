"""Writes the OpenAPI document the web panel generates its client from.

    python -m kasbbook.api.openapi_export web/openapi.json

Committed next to the panel so a change to the API shows up as a diff in the
client that depends on it.
"""

from __future__ import annotations

import json
import sys

from ..shared.settings import Settings
from .app import create_app


def main(target: str) -> None:
    # Building the app reads no database and no network; the lifespan, which
    # does, is never started.
    app = create_app(settings=Settings(database_url="sqlite+aiosqlite://", api_secret_key="export"))
    with open(target, "w", encoding="utf-8") as out:
        json.dump(app.openapi(), out, ensure_ascii=False, indent=2, sort_keys=True)
        out.write("\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
