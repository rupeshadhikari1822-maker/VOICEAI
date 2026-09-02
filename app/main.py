"""Application factory and wiring. No business logic belongs in this file.

Routes live in `app/api/routes/`, domain logic in `app/services/`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.db import create_all
from app.services.consent import verify_consent_available
from app.services.storage import StorageError

logger = logging.getLogger("voice")

_STATIC_DIR = get_settings().base_dir / "static"
_RECORDER_INDEX = _STATIC_DIR / "recorder" / "index.html"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Loading consent text is lazy and cached, so without this the failure
    # would surface on the first contributor's request instead of at startup.
    verify_consent_available()

    # create_all() only ever adds missing tables -- it cannot add a column to an
    # existing one. Schema changes go through Alembic (`alembic upgrade head`).
    create_all()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="voice.cloudfrm.ai", version="0.2.0", lifespan=lifespan)

    app.include_router(api_router)

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_RECORDER_INDEX)

    @app.exception_handler(StorageError)
    async def _storage_error_handler(_request: Request, exc: StorageError):
        logger.error("storage error: %s", exc)
        return JSONResponse({"detail": "storage error"}, status_code=502)

    return app


app = create_app()
