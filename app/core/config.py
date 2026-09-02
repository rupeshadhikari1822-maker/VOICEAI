from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: this file is app/core/config.py, so go up three levels.
# Keep this in step with the file's location -- everything that resolves
# static/, docs/ and the default SQLite path hangs off it.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Everything is overridable from .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- database -----------------------------------------------------
    database_url: str = f"sqlite:///{(BASE_DIR / 'voice.db').as_posix()}"

    # --- object storage ----------------------------------------------
    # "local" writes to ./storage_local and needs no cloud account.
    # "s3" talks to any S3-compatible endpoint (R2, B2, Wasabi, MinIO).
    storage_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_bucket: str = "voice-corpus"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    local_storage_dir: Path = BASE_DIR / "storage_local"

    # --- app ----------------------------------------------------------
    public_base_url: str = "http://localhost:8000"
    secret_key: str = "dev-insecure-change-me"
    presign_ttl_s: int = 900
    max_clip_bytes: int = 40 * 1024 * 1024

    # --- consent ------------------------------------------------------
    consent_version: str = "2026-09-01-v1"

    # --- QC gate ------------------------------------------------------
    # The corpus profile decides how strict the SNR gate is.
    # "asr" -> 30 dB, "tts" -> 40 dB.
    qc_profile: str = "asr"

    @property
    def base_dir(self) -> Path:
        return BASE_DIR


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
