"""Shared FastAPI dependencies.

Anything more than one route module needs goes here, so route modules stay
about their own resource.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Query

from app.core.config import get_settings
from app.core.db import get_db  # noqa: F401  (re-exported: routes import it here)
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
