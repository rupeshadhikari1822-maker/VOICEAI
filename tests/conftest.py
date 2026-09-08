"""Test sandbox and shared fixtures.

Everything is redirected to a temp SQLite file and a temp storage directory
**before** any app module is imported, so running the suite can never touch a
real corpus. That ordering is why the environment is set at module scope here
rather than in a fixture.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="voice-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP.as_posix()}/test.db"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["SECRET_KEY"] = "test-key-not-a-real-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"

from app.core.db import SessionLocal, create_all  # noqa: E402
from app.models import Prompt  # noqa: E402

SANDBOX = _TMP

# --- fake Supabase auth tokens ---------------------------------------------
#
# Recording requires a signed-in account (POST /api/speakers), and real
# Supabase tokens are signed ES256 via a per-project key pair fetched as a
# public JWKS (app/core/accounts.py) -- there's no shared secret to forge a
# token with. So every test that needs "a signed-in contributor" signs with
# this throwaway key pair instead, and the autouse fixture below stands in for
# the JWKS endpoint so nothing here ever makes a real network call.

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
# A second, unrelated key pair: signing with this one must fail verification
# against the "real" public key above, exactly like a forged token would.
_WRONG_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_PUBLIC_KEY)


@pytest.fixture(autouse=True)
def _fake_jwks(monkeypatch):
    """No network in tests: stand in for Supabase's public JWKS endpoint."""
    monkeypatch.setattr("app.core.accounts._jwks_client", lambda: _FakeJWKClient())


def auth_token(sub: str, email: str = "person@example.com", private_key=_PRIVATE_KEY) -> str:
    """A valid (or, with `private_key=WRONG_PRIVATE_KEY`, forged) session token."""
    return jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated"},
        private_key,
        algorithm="ES256",
    )


def auth_headers(sub: str = "test-contributor") -> dict[str, str]:
    """`Authorization` header for a signed-in speaker in tests that don't
    otherwise care which account it is -- most speaker-creation calls."""
    return {"Authorization": f"Bearer {auth_token(sub)}"}


WRONG_PRIVATE_KEY = _WRONG_PRIVATE_KEY


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    create_all()


@pytest.fixture(scope="session")
def prompts() -> list[str]:
    """A handful of active prompts, enough for any flow test."""
    ids = [f"ne-test-{i}" for i in range(1, 9)]
    texts = [
        "नमस्ते, तपाईंलाई कस्तो छ?",
        "आज मौसम राम्रो छ।",
        "मलाई नेपाली भाषा मन पर्छ।",
        "यो बाटो कता जान्छ?",
        "पानी उमालेर मात्र पिउनुहोस्।",
        "भोलि बिहान सात बजे भेटौँ।",
        "ज्ञान बाँड्दा घट्दैन, बढ्छ।",
        "अन्त्यमा, सबैलाई धन्यवाद।",
    ]
    with SessionLocal() as db:
        for pid, text in zip(ids, texts):
            if db.get(Prompt, pid) is None:
                db.add(Prompt(id=pid, lang="ne", text=text, active=True))
        db.commit()
    return ids


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def consent_version(client) -> str:
    return client.get("/api/config").json()["consent"]["version"]
