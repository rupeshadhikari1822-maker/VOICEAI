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

import pytest

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
