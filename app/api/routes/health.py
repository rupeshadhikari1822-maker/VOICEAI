"""Liveness and client configuration."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import get_thresholds
from app.core.config import get_settings
from app.services.consent import consent_payload

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@router.get("/api/config")
def api_config() -> dict:
    """Everything the recorder needs to configure itself and gate takes locally."""
    thresholds = get_thresholds()
    return {
        "audio": {
            "sample_rate": thresholds.target_sample_rate,
            "bit_depth": 16,
            "channels": 1,
        },
        "qc": {
            "min_snr_db": thresholds.min_snr_db,
            "min_peak_dbfs": thresholds.min_peak_dbfs,
            "max_peak_dbfs": thresholds.max_peak_dbfs,
            "ideal_min_peak_dbfs": thresholds.ideal_min_peak_dbfs,
            "ideal_max_peak_dbfs": thresholds.ideal_max_peak_dbfs,
            "max_clipping_ratio": thresholds.max_clipping_ratio,
            "max_noise_floor_dbfs": thresholds.max_noise_floor_dbfs,
            "min_duration_s": thresholds.min_duration_s,
            "max_duration_s": thresholds.max_duration_s,
            "ideal_min_duration_s": thresholds.ideal_min_duration_s,
            "ideal_max_duration_s": thresholds.ideal_max_duration_s,
        },
        "consent": consent_payload(),
        "profile": get_settings().qc_profile,
    }
