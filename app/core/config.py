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

    # --- review: auth -------------------------------------------------
    # Named staff tokens, "alice:tok1,bob:tok2". Reviewers are trusted staff,
    # not the public; this is deliberately not an identity system.
    reviewer_tokens: str = ""
    # Playback URLs are short-lived. The bucket stays private -- a review UI is
    # the easiest place to accidentally make a corpus public.
    presign_get_ttl_s: int = 300

    # --- review: ASR pre-filter ---------------------------------------
    # Thresholds are per-language in practice: a normaliser that is slightly off
    # for a script will shift CER for every clip in it, so these are configurable
    # rather than baked in.
    asr_model: str = "small"
    asr_auto_verify_cer: float = 0.10
    asr_auto_reject_cer: float = 0.40

    # --- review: queue policy -----------------------------------------
    # Review every one of a speaker's first N clips, then sample, because
    # speaker quality is strongly autocorrelated -- good readers stay good.
    review_warmup_clips: int = 20
    review_sample_fraction: float = 0.10
    # Snap back to reviewing everything if a speaker's rejection rate exceeds
    # this once they are past warm-up.
    review_reject_rate_trigger: float = 0.20
    # Reviewer fatigue produces bad labels; the UI suggests stopping after this.
    review_session_minutes: int = 45

    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def reviewers(self) -> dict[str, str]:
        """Parsed `REVIEWER_TOKENS` as {name: token}. Empty means review is off."""
        out: dict[str, str] = {}
        for pair in self.reviewer_tokens.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            name, _, token = pair.partition(":")
            name, token = name.strip(), token.strip()
            if name and token:
                out[name] = token
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
