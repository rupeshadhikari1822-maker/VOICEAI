"""The staff dashboard: same trust boundary as /review, a reviewer token."""

from __future__ import annotations

import io
import json
import os
import zipfile

import pytest

from app.core.admin_auth import hash_password
from app.core.config import get_settings
from tests.test_smoke import PII, make_speaker, upload
from tests.synth import clean_take

TOKEN = "test-admin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"
ADMIN_TOKEN = "test-admin-login-token"


def record_a_passed_clip(client, consent_version, prompts):
    """Same four calls test_overview_reports_real_counts uses to get one
    passed clip into the corpus -- the export tests below need at least one.

    Returns (speaker_id, clip_id). The corpus is a shared, session-scoped
    sandbox across the whole test run -- other modules (test_accounts.py's
    `_make_clip`, for instance) plant "passed" clips with no real object
    behind them. An export test must key off *this* clip specifically, not
    "any file under train/", or it becomes order-dependent on what else has
    run first.
    """
    speaker_id = make_speaker(client, consent_version)
    session_id = client.post("/api/sessions", json={"speaker_id": speaker_id}).json()[
        "session_id"
    ]
    prompt_id = client.get(f"/api/prompts?session_id={session_id}").json()[0]["id"]
    init = client.post(
        "/api/clips/init", json={"session_id": session_id, "prompt_id": prompt_id}
    ).json()
    upload(client, init["upload"]["url"], clean_take())
    client.post(f"/api/clips/{init['clip_id']}/complete", json={})
    return speaker_id, init["clip_id"]


@pytest.fixture(scope="module", autouse=True)
def _reviewer_configured():
    previous = os.environ.get("REVIEWER_TOKENS")
    os.environ["REVIEWER_TOKENS"] = f"admin-tester:{TOKEN}"
    get_settings.cache_clear()
    yield
    if previous is None:
        os.environ.pop("REVIEWER_TOKENS", None)
    else:
        os.environ["REVIEWER_TOKENS"] = previous
    get_settings.cache_clear()


@pytest.fixture
def admin_login_configured():
    """Layers ADMIN_EMAIL/ADMIN_PASSWORD_HASH and an "admin" REVIEWER_TOKENS
    entry on top of the module fixture's "admin-tester" one, then restores
    exactly what was there before."""
    previous = {
        "ADMIN_EMAIL": os.environ.get("ADMIN_EMAIL"),
        "ADMIN_PASSWORD_HASH": os.environ.get("ADMIN_PASSWORD_HASH"),
        "REVIEWER_TOKENS": os.environ.get("REVIEWER_TOKENS"),
    }
    os.environ["ADMIN_EMAIL"] = ADMIN_EMAIL
    os.environ["ADMIN_PASSWORD_HASH"] = hash_password(ADMIN_PASSWORD)
    os.environ["REVIEWER_TOKENS"] = f"admin-tester:{TOKEN},admin:{ADMIN_TOKEN}"
    get_settings.cache_clear()
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


def test_admin_login_page_is_public(client):
    res = client.get("/admin/login")
    assert res.status_code == 200
    assert b"<html" in res.content.lower()


def test_login_disabled_when_admin_not_configured(client):
    # The module fixture sets REVIEWER_TOKENS but never ADMIN_EMAIL/HASH.
    res = client.post(
        "/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert res.status_code == 401


def test_login_succeeds_and_returns_the_admin_token(client, admin_login_configured):
    res = client.post(
        "/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["token"] == ADMIN_TOKEN
    assert body["reviewer"] == "admin"

    # The returned token is a real reviewer token -- it must actually work.
    res = client.get(
        "/api/admin/overview", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert res.status_code == 200


def test_login_rejects_wrong_password(client, admin_login_configured):
    res = client.post(
        "/api/admin/login", json={"email": ADMIN_EMAIL, "password": "not it"}
    )
    assert res.status_code == 401


def test_login_rejects_unknown_email(client, admin_login_configured):
    res = client.post(
        "/api/admin/login",
        json={"email": "someone-else@example.com", "password": ADMIN_PASSWORD},
    )
    assert res.status_code == 401


def test_admin_page_redirects_to_login_without_a_reviewer_token(client):
    res = client.get("/admin", follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert res.headers["location"] == "/admin/login"


def test_admin_page_redirects_to_login_with_a_wrong_token(client):
    res = client.get("/admin?token=not-a-real-token", follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert res.headers["location"] == "/admin/login"


def test_admin_page_loads_with_a_valid_token(client):
    res = client.get("/admin", headers=AUTH)
    assert res.status_code == 200
    assert b"<html" in res.content.lower()


def test_overview_requires_auth(client):
    assert client.get("/api/admin/overview").status_code == 401


def test_overview_reports_real_counts(client, consent_version, prompts):
    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    prompt_id = client.get(f"/api/prompts?session_id={session_id}").json()[0]["id"]
    init = client.post(
        "/api/clips/init", json={"session_id": session_id, "prompt_id": prompt_id}
    ).json()
    upload(client, init["upload"]["url"], clean_take())
    client.post(f"/api/clips/{init['clip_id']}/complete", json={})

    res = client.get("/api/admin/overview", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["speakers"]["total"] >= 1
    assert body["clips"]["total"] >= 1
    assert body["clips"]["passed"] >= 1
    assert "active_uncovered" in body["prompts"]


def test_speakers_list_requires_auth(client):
    assert client.get("/api/admin/speakers").status_code == 401


def test_speakers_list_includes_a_known_speaker(client, consent_version):
    speaker_id = make_speaker(client, consent_version)
    res = client.get("/api/admin/speakers?limit=200", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    ids = [s["speaker_id"] for s in body["speakers"]]
    assert speaker_id in ids
    row = next(s for s in body["speakers"] if s["speaker_id"] == speaker_id)
    assert row["name"] == PII["name"]
    assert row["linked_account"] is False


def test_export_requires_auth(client):
    assert client.get("/api/admin/export?format=asr").status_code == 401


def test_export_downloads_a_zip_with_no_pii(client, consent_version, prompts):
    _speaker_id, clip_id = record_a_passed_clip(client, consent_version, prompts)

    res = client.get("/api/admin/export?format=asr&sr=16000", headers=AUTH)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "attachment" in res.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = zf.namelist()
        assert "manifest.jsonl" in names
        assert "DATASET_CARD.md" in names

        manifest_text = zf.read("manifest.jsonl").decode("utf-8")
        card_text = zf.read("DATASET_CARD.md").decode("utf-8")

        # Key off this test's own clip, not "any wav somewhere" -- the corpus
        # is a shared sandbox across the whole test run, and other modules
        # plant "passed" clips with no real object behind them.
        rows = [json.loads(line) for line in manifest_text.splitlines()]
        row = next(r for r in rows if r["id"] == clip_id)
        assert row["audio_filepath"] in names
        assert row["audio_filepath"].endswith(".wav")

    # The same PII fence as scripts/export_dataset.py -- exercised here through
    # the admin download endpoint rather than the CLI.
    for value in PII.values():
        assert value not in manifest_text
        assert value not in card_text
    assert "caste_ethnicity" not in manifest_text


def test_export_reports_no_clips_as_404_not_a_crash(client, consent_version):
    res = client.get(
        "/api/admin/export?format=asr&min_snr=999",
        headers=AUTH,
    )
    assert res.status_code == 404
