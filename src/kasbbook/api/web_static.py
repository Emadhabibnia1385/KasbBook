"""Serves the web panel from the same process as the API.

One origin means no CORS and no second place to deploy. The built panel is
committed (`web/dist`) so the server never needs a JavaScript toolchain.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

DEFAULT_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"

# Never answered with the panel: an unknown API path must stay a 404, or a
# client would parse HTML as JSON and fail somewhere far from the cause.
_API_PREFIXES = ("api/", "docs", "openapi.json", "healthz", "readyz")

IMMUTABLE = "public, max-age=31536000, immutable"
# The shell and the service worker are what point at the hashed assets, so a
# cached copy of either would pin a visitor to an old build.
REVALIDATE = "no-cache"


def mount_web(app: FastAPI, dist: Path | None = None) -> bool:
    root = Path(dist or os.environ.get("KASBBOOK_WEB_DIST") or DEFAULT_DIST).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    @app.get("/{path:path}", include_in_schema=False)
    async def panel(path: str) -> FileResponse:
        if path.startswith(_API_PREFIXES):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        # Inside the build folder only: `..` must not reach the .env beside it.
        if path and candidate.is_file() and root in candidate.parents:
            cache = IMMUTABLE if path.startswith("assets/") else REVALIDATE
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": REVALIDATE})

    return True
