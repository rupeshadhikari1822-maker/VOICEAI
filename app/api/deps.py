"""Shared FastAPI dependencies.

Anything more than one route module needs goes here, so route modules stay
about their own resource.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException, Query

from app.core.config import get_settings
from app.core.db import get_db  # noqa: F401  (re-exported: routes import it here)
from app.core.security import ReviewAuthError, extract_token, reviewer_for_token
from app.services.audio_qc import QCThresholds


@lru_cache(maxsize=1)
def get_thresholds() -> QCThresholds:
    """The QC gate for the configured corpus profile (asr: 30 dB, tts: 40 dB)."""
    return QCThresholds.for_profile(get_settings().qc_profile)


def pagination(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, int]:
    return {"limit": limit, "offset": offset}


def current_reviewer(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    """The authenticated reviewer's name, for `verified_by` and ReviewEvent.

    Accepts `Authorization: Bearer <tok>` or `?token=<tok>`; the query form is
    needed because the page is opened from a pasted link and `<audio src>`
    cannot carry a header.
    """
    try:
        return reviewer_for_token(extract_token(authorization, token))
    except ReviewAuthError as exc:
        raise HTTPException(
            401, str(exc), headers={"WWW-Authenticate": "Bearer"}
        ) from exc
