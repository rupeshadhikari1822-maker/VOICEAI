from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: this file is app/core/config.py, so go up three levels.
# Keep this in step with the file's location -- everything that resolves
# static/, docs/ and the default SQLite path hangs off it.
BASE_DIR = Path(__file__).resolve().parents[2]

# The value shipped in .env.example. If this reaches production, anyone who can
# read the repo can forge upload URLs.
DEFAULT_SECRET_KEY = "dev-insecure-change-me"


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
    # Set ENVIRONMENT=production on a real deployment. It switches on the
    # startup guard below, which refuses to boot in a configuration that would
    # quietly lose or expose contributor data.
    environment: str = "development"
    # Deliberate, named opt-out for a single-contributor pilot. SQLite is fine
    # when one person records at a time; it fails under concurrency with
    # "database is locked", which surfaces as an upload the contributor cannot
    # retry. You must set this knowingly -- it is never the default.
    allow_sqlite_in_production: bool = False
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
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @model_validator(mode="after")
    def _guard_s3_endpoint(self) -> "Settings":
        """Reject a malformed R2/S3 endpoint at boot, not at the first upload.

        The R2 console shows the endpoint with the bucket already appended
        (`https://<acct>.r2.cloudflarestorage.com/voice-corpus`), and pasting it
        verbatim is the natural thing to do. boto3 then builds every key under
        that path, and the failure arrives much later as a 404 on an upload,
        which reads as a missing object rather than a wrong endpoint.

        Runs whenever the backend is s3, not only in production: the failure is
        identical either way.
        """
        if self.storage_backend.strip().lower() != "s3":
            return self

        endpoint = (self.s3_endpoint_url or "").strip()
        problems: list[str] = []

        if not endpoint:
            problems.append("S3_ENDPOINT_URL is empty.")
        else:
            if "<" in endpoint or ">" in endpoint:
                problems.append(
                    f"S3_ENDPOINT_URL still contains a placeholder: {endpoint!r}. "
                    "Substitute your Cloudflare account ID."
                )
            parsed = urlparse(endpoint)
            if parsed.scheme != "https":
                problems.append(
                    f"S3_ENDPOINT_URL must be https, got {parsed.scheme or 'no scheme'!r}."
                )
            if not parsed.netloc:
                problems.append(f"S3_ENDPOINT_URL has no host: {endpoint!r}.")
            # The one that actually bites.
            if parsed.path.strip("/"):
                problems.append(
                    f"S3_ENDPOINT_URL has a path on it: {parsed.path!r}. The R2 "
                    "console shows the bucket appended, but the app adds the "
                    "bucket name itself. Use just the host: "
                    f"https://{parsed.netloc}"
                )

        if problems:
            listed = "\n".join(f"  {n}. {p}" for n, p in enumerate(problems, 1))
            raise ValueError(
                "\n\nrefusing to start: S3_ENDPOINT_URL is not usable\n\n"
                f"{listed}\n"
            )

        return self

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        """Refuse to boot a production deployment that is misconfigured.

        `scripts/check_deployment.py` catches these from outside, but only if
        somebody runs it. This makes the bad states unreachable: the process
        will not start, so there is no window in which a contributor records
        into a deployment that cannot keep their audio.

        Every problem is reported at once. Finding a second one after fixing
        the first, on a box you are SSH'd into, is a waste of a deploy.
        """
        if not self.is_production:
            return self

        problems: list[str] = []

        if self.storage_backend.strip().lower() != "s3":
            problems.append(
                "STORAGE_BACKEND is not 's3'. Clips would land on this box's "
                "disk, with no versioning and no second copy, and every byte "
                "would flow through the API process."
            )

        if self.database_url.strip().lower().startswith("sqlite") and not (
            self.allow_sqlite_in_production
        ):
            problems.append(
                "DATABASE_URL is SQLite. Concurrent recording sessions produce "
                "'database is locked', which fails an upload the contributor "
                "cannot retry. Use Postgres, or set "
                "ALLOW_SQLITE_IN_PRODUCTION=true for a single-contributor pilot."
            )

        if not self.public_base_url.strip().lower().startswith("https://"):
            problems.append(
                f"PUBLIC_BASE_URL is {self.public_base_url!r}, not https. "
                "getUserMedia requires a secure context, so the microphone "
                "would never open."
            )

        if self.secret_key.strip() == DEFAULT_SECRET_KEY or not self.secret_key.strip():
            problems.append(
                "SECRET_KEY is unset or still the repo default. Generate one: "
                'python -c "import secrets;print(secrets.token_hex(32))"'
            )

        if problems:
            listed = "\n".join(f"  {n}. {p}" for n, p in enumerate(problems, 1))
            raise ValueError(
                "\n\n"
                "refusing to start: ENVIRONMENT=production with an unsafe configuration\n\n"
                f"{listed}\n\n"
                "Fix /srv/voice/.env and restart. To run locally with these\n"
                "settings, unset ENVIRONMENT or set it to 'development'.\n"
            )

        return self

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
