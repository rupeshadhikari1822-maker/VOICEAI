"""The production startup guard and the storage preflight.

Both exist for the same reason: a misconfiguration that no server-side check
notices, discovered only when a real contributor loses a session to it.
"""

from __future__ import annotations

import pytest

from app.core.config import DEFAULT_SECRET_KEY, Settings

PROD = {
    "environment": "production",
    "storage_backend": "s3",
    # Required once the backend is s3: the endpoint validator runs first.
    "s3_endpoint_url": "https://a1b2c3.r2.cloudflarestorage.com",
    "database_url": "postgresql+psycopg://u:p@localhost/voice",
    "public_base_url": "https://record.cloudfrm.ai",
    "secret_key": "a" * 64,
}


# --- B1: startup guard --------------------------------------------------


def test_a_correct_production_config_boots():
    settings = Settings(**PROD)
    assert settings.is_production


def test_development_is_never_guarded():
    """Local development must keep working with settings production forbids."""
    settings = Settings(
        environment="development",
        storage_backend="local",
        database_url="sqlite:///voice.db",
        public_base_url="http://localhost:8000",
        secret_key=DEFAULT_SECRET_KEY,
    )
    assert settings.is_production is False


def test_production_refuses_local_storage():
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        Settings(**{**PROD, "storage_backend": "local"})


def test_production_refuses_plain_http():
    """getUserMedia needs a secure context; http means the mic never opens."""
    with pytest.raises(ValueError, match="PUBLIC_BASE_URL"):
        Settings(**{**PROD, "public_base_url": "http://record.cloudfrm.ai"})


def test_production_refuses_the_default_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(**{**PROD, "secret_key": DEFAULT_SECRET_KEY})


def test_production_refuses_an_empty_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(**{**PROD, "secret_key": "   "})


def test_production_refuses_sqlite_by_default():
    with pytest.raises(ValueError, match="SQLite"):
        Settings(**{**PROD, "database_url": "sqlite:///voice.db"})


def test_sqlite_allowed_only_with_the_explicit_pilot_opt_out():
    settings = Settings(
        **{**PROD, "database_url": "sqlite:///voice.db"},
        allow_sqlite_in_production=True,
    )
    assert settings.is_production


def test_every_problem_is_reported_at_once():
    """Finding a second fault after fixing the first wastes a deploy."""
    with pytest.raises(ValueError) as exc:
        Settings(
            environment="production",
            storage_backend="local",
            database_url="sqlite:///voice.db",
            public_base_url="http://record.cloudfrm.ai",
            secret_key=DEFAULT_SECRET_KEY,
        )
    message = str(exc.value)
    for expected in ("STORAGE_BACKEND", "SQLite", "PUBLIC_BASE_URL", "SECRET_KEY"):
        assert expected in message, f"{expected} missing from the guard output"
    assert "4." in message, "should enumerate all four"


@pytest.mark.parametrize("value", ["production", "PRODUCTION", " prod "])
def test_production_is_recognised_case_and_space_insensitively(value):
    with pytest.raises(ValueError):
        Settings(**{**PROD, "environment": value, "storage_backend": "local"})


@pytest.mark.parametrize("value", ["development", "staging", "", "dev"])
def test_non_production_environments_are_not_guarded(value):
    """Only 'production' locks down; staging should stay convenient."""
    assert Settings(environment=value, storage_backend="local").is_production is False


# --- B2: storage preflight ----------------------------------------------


def test_preflight_returns_a_usable_presigned_put(client):
    body = client.get("/api/storage/preflight").json()
    assert body["method"] == "PUT"
    assert body["probe_bytes"] == 1024
    assert body["url"]
    assert body["headers"]["Content-Type"] == "application/octet-stream"
    assert body["expires_at"] > 0


def test_preflight_probe_is_outside_every_export_prefix(client):
    """A probe object must never be mistaken for corpus audio."""
    from urllib.parse import parse_qs, urlparse

    body = client.get("/api/storage/preflight").json()
    key = parse_qs(urlparse(body["url"]).query)["key"][0]
    assert key.startswith("_preflight/")
    for corpus_prefix in ("raw/", "derived/", "consent/"):
        assert not key.startswith(corpus_prefix)


def test_preflight_admits_when_it_proves_nothing(client):
    """On the local backend the PUT is same-origin and exercises no CORS."""
    body = client.get("/api/storage/preflight").json()
    assert body["same_origin"] is True
    assert body["backend"] == "local"


def test_preflight_names_a_control_url_for_disambiguation(client):
    """A CORS rejection and a network failure are the same opaque TypeError.

    The client separates them by asking whether our own origin is reachable,
    so the endpoint has to tell it where to ask.
    """
    body = client.get("/api/storage/preflight").json()
    assert body["control_url"] == "/healthz"
    assert client.get(body["control_url"]).status_code == 200


def test_the_preflight_put_actually_works(client):
    """End to end: the URL handed out is genuinely writable."""
    from urllib.parse import urlparse

    body = client.get("/api/storage/preflight").json()
    parsed = urlparse(body["url"])
    res = client.put(
        f"{parsed.path}?{parsed.query}",
        content=b"\x00" * body["probe_bytes"],
        headers=body["headers"],
    )
    assert res.status_code == 200


def test_each_preflight_uses_a_fresh_key(client):
    from urllib.parse import parse_qs, urlparse

    keys = {
        parse_qs(urlparse(client.get("/api/storage/preflight").json()["url"]).query)["key"][0]
        for _ in range(3)
    }
    assert len(keys) == 3, "probe keys must not collide between sessions"


# --- B6: probes must never reach the archive ----------------------------


def test_backup_prefixes_exclude_preflight_probes():
    """An allow-list, so a new prefix is excluded by default.

    If this ever became a skip-list, or grew to cover the whole bucket, every
    session's 1 KB probe would replicate to the offsite archive forever.
    """
    from scripts.backup_corpus import BACKUP_PREFIXES, PREFLIGHT_PREFIX

    assert BACKUP_PREFIXES == ("raw/", "consent/")
    assert PREFLIGHT_PREFIX not in BACKUP_PREFIXES
    assert not any(PREFLIGHT_PREFIX.startswith(p) for p in BACKUP_PREFIXES)
    # derived/ regenerates from raw/; backing it up doubles the bill.
    assert "derived/" not in BACKUP_PREFIXES


def test_backup_copies_corpus_audio_but_not_probes(tmp_path):
    """End to end against real objects, not just the constant."""
    from app.core.config import get_settings
    from app.services.storage import LocalStorage
    from scripts.backup_corpus import copy_objects

    storage = LocalStorage(get_settings())
    storage.put_bytes("raw/ne/BACKUPTEST/SES/CLIP.wav", b"audio-bytes")
    storage.put_bytes("_preflight/PROBE.bin", b"\x00" * 1024)
    storage.put_bytes("derived/16k/ne/BACKUPTEST/CLIP.wav", b"regenerable")

    copy_objects(storage, tmp_path, dry_run=False)

    assert (tmp_path / "raw/ne/BACKUPTEST/SES/CLIP.wav").is_file()
    assert not (tmp_path / "_preflight").exists(), "probes must not be archived"
    assert not (tmp_path / "derived").exists(), "derived/ rebuilds from raw/"


# --- structure ----------------------------------------------------------


def test_app_root_holds_only_the_entry_point():
    """Every module belongs to core/, api/, models/, schemas/ or services/.

    A file loose in app/ is a sign someone could not decide which concern it
    served. This is the moment to decide, not defer -- the last stray was a
    compatibility shim that outlived its own justification and left two import
    paths for one thing with no rule about which to use.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "app"
    loose = sorted(p.name for p in root.glob("*.py"))
    assert loose == ["__init__.py", "main.py"], (
        f"unexpected module(s) in app/ root: {loose}. "
        "Move it into core/, api/, models/, schemas/ or services/."
    )


# --- S3 endpoint format -------------------------------------------------

S3 = {"storage_backend": "s3", "s3_access_key_id": "k", "s3_secret_access_key": "s"}


def test_correct_endpoint_is_accepted():
    Settings(**S3, s3_endpoint_url="https://a1b2c3.r2.cloudflarestorage.com")


def test_trailing_slash_is_tolerated():
    """Harmless; boto3 normalises it. Only a real path is a problem."""
    Settings(**S3, s3_endpoint_url="https://a1b2c3.r2.cloudflarestorage.com/")


def test_endpoint_with_the_bucket_appended_is_refused():
    """The R2 console shows the bucket on the end, so pasting it is natural.

    Left alone, boto3 nests every key under that path and the failure arrives
    much later as a 404 on an upload -- which reads as a missing object rather
    than a wrong endpoint.
    """
    with pytest.raises(ValueError, match="path on it"):
        Settings(**S3, s3_endpoint_url="https://a1b2c3.r2.cloudflarestorage.com/voice-corpus")


def test_unsubstituted_placeholder_is_refused():
    with pytest.raises(ValueError, match="placeholder"):
        Settings(**S3, s3_endpoint_url="https://<account_id>.r2.cloudflarestorage.com")


def test_non_https_endpoint_is_refused():
    with pytest.raises(ValueError, match="must be https"):
        Settings(**S3, s3_endpoint_url="http://a1b2c3.r2.cloudflarestorage.com")


def test_empty_endpoint_is_refused_when_backend_is_s3():
    with pytest.raises(ValueError, match="empty"):
        Settings(**S3, s3_endpoint_url="")


def test_local_backend_ignores_the_endpoint_entirely():
    """Development must not be dragged into S3 validation."""
    assert Settings(storage_backend="local", s3_endpoint_url="nonsense").is_production is False
