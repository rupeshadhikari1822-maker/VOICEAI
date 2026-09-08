"""Account linking: a signed-in contributor's recordings stay theirs.

`POST /api/speakers` requires a signed-in Supabase session and sets
`speakers.user_id` from it; one account can never see another account's
speaker profiles. A speaker with no linked account can still exist from
before that requirement, so a handful of tests below simulate one directly
against the database rather than through the API, which can no longer
produce one.

Real Supabase tokens are signed ES256 via a per-project key pair, fetched by
the app as a public JWKS (app/core/accounts.py) -- there is no shared secret
to forge a token with. `tests/conftest.py` generates a throwaway EC key pair
and monkeypatches the JWKS client to hand back its public half, instead of
ever making a real network call.
"""

from __future__ import annotations

from app.core.db import SessionLocal
from app.core.ids import new_ulid
from app.models import Clip, ConsentRecord, RecordingSession, Speaker
from app.services.consent import consent_sha256
from tests.conftest import WRONG_PRIVATE_KEY, auth_token as _token
from tests.test_smoke import PII


def _make_legacy_anonymous_speaker(db, consent_version) -> str:
    """A speaker with no linked account, as could exist from before signing
    in became mandatory to record at all. Inserted directly because the API
    can no longer create one."""
    speaker = Speaker(id=new_ulid(), user_id=None, **PII)
    db.add(speaker)
    db.add(
        ConsentRecord(
            id=new_ulid(),
            speaker_id=speaker.id,
            version=consent_version,
            text_sha256=consent_sha256(),
            commercial_use=True,
        )
    )
    db.commit()
    return speaker.id


def _signup(client, consent_version, headers=None, **overrides):
    payload = {
        **PII,
        "province": "बागमती",
        "district": "काठमाडौं",
        "mother_tongue": "नेपाली",
        "age_band": "25-34",
        "gender": "female",
        "consent": {
            "version": consent_version,
            "accepted": True,
            "commercial_use": True,
        },
        **overrides,
    }
    res = client.post("/api/speakers", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["speaker_id"]


def test_signup_without_an_account_is_refused(client, consent_version):
    res = client.post(
        "/api/speakers",
        json={
            **PII,
            "consent": {
                "version": consent_version,
                "accepted": True,
                "commercial_use": True,
            },
        },
    )
    assert res.status_code == 401


def test_signed_in_signup_links_user_id(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-alice')}"},
    )
    with SessionLocal() as db:
        assert db.get(Speaker, speaker_id).user_id == "user-alice"


def test_signup_with_a_forged_token_is_refused(client, consent_version):
    forged = _token("user-mallory", private_key=WRONG_PRIVATE_KEY)
    res = client.post(
        "/api/speakers",
        json={
            **PII,
            "consent": {
                "version": consent_version,
                "accepted": True,
                "commercial_use": True,
            },
        },
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert res.status_code == 401


def test_export_row_never_reaches_user_id(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-bob')}"},
    )
    with SessionLocal() as db:
        row = db.get(Speaker, speaker_id).export_row()
    assert "user_id" not in row


def test_me_speakers_requires_auth(client):
    res = client.get("/api/me/speakers")
    assert res.status_code == 401


def test_me_speakers_returns_only_own(client, consent_version):
    mine = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-carol')}"},
    )
    _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-dave')}"},
    )

    res = client.get(
        "/api/me/speakers",
        headers={"Authorization": f"Bearer {_token('user-carol')}"},
    )
    assert res.status_code == 200
    ids = [row["speaker_id"] for row in res.json()]
    assert ids == [mine]


# --- linking a speaker to an account after the fact -----------------------
# The common path: consent creates an anonymous speaker before anyone could
# have signed in, so the account has to be attached retroactively once they do.


def test_link_account_attaches_an_anonymous_speaker(client, consent_version):
    with SessionLocal() as db:
        speaker_id = _make_legacy_anonymous_speaker(db, consent_version)

    res = client.post(
        f"/api/speakers/{speaker_id}/link-account",
        headers={"Authorization": f"Bearer {_token('user-erin')}"},
    )
    assert res.status_code == 200, res.text
    with SessionLocal() as db:
        assert db.get(Speaker, speaker_id).user_id == "user-erin"

    # And it now shows up for that account.
    mine = client.get(
        "/api/me/speakers",
        headers={"Authorization": f"Bearer {_token('user-erin')}"},
    ).json()
    assert [row["speaker_id"] for row in mine] == [speaker_id]


def test_link_account_is_idempotent_for_the_same_account(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-frank')}"},
    )
    res = client.post(
        f"/api/speakers/{speaker_id}/link-account",
        headers={"Authorization": f"Bearer {_token('user-frank')}"},
    )
    assert res.status_code == 200


def test_link_account_refuses_to_hijack_another_accounts_speaker(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-grace')}"},
    )
    res = client.post(
        f"/api/speakers/{speaker_id}/link-account",
        headers={"Authorization": f"Bearer {_token('user-henry')}"},
    )
    assert res.status_code == 409
    with SessionLocal() as db:
        assert db.get(Speaker, speaker_id).user_id == "user-grace"


def test_link_account_requires_auth(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-ivan')}"},
    )
    res = client.post(f"/api/speakers/{speaker_id}/link-account")
    assert res.status_code == 401


def test_link_unknown_speaker_404s(client):
    res = client.post(
        "/api/speakers/does-not-exist/link-account",
        headers={"Authorization": f"Bearer {_token('user-irene')}"},
    )
    assert res.status_code == 404


# --- profile page: full profile, recordings, playback, edit ownership ------


def _make_clip(db, speaker_id, session_id, text="परीक्षण वाक्य।", qc_status="passed"):
    clip = Clip(
        id=new_ulid(),
        session_id=session_id,
        speaker_id=speaker_id,
        prompt_id="ne-0001",
        prompt_text=text,
        lang="ne",
        object_key=f"raw/ne/{speaker_id}/{session_id}/{new_ulid()}.wav",
        qc_status=qc_status,
    )
    db.add(clip)
    db.commit()
    return clip.id


def test_my_profile_requires_auth(client):
    assert client.get("/api/me/profile").status_code == 401


def test_my_profile_404s_with_no_linked_speaker(client):
    res = client.get(
        "/api/me/profile", headers={"Authorization": f"Bearer {_token('user-jill')}"}
    )
    assert res.status_code == 404


def test_my_profile_returns_fields_and_clips(client, consent_version, db):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-kevin')}"},
    )
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    _make_clip(db, speaker_id, session_id, text="बिरामीलाई तुरुन्तै अस्पताल लैजानुपर्छ।")

    res = client.get(
        "/api/me/profile", headers={"Authorization": f"Bearer {_token('user-kevin')}"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["speaker_id"] == speaker_id
    assert body["name"] == PII["name"]
    assert len(body["clips"]) == 1
    assert body["clips"][0]["prompt_text"] == "बिरामीलाई तुरुन्तै अस्पताल लैजानुपर्छ।"
    assert body["clips"][0]["qc_status"] == "passed"


def test_listen_to_own_clip_returns_a_url(client, consent_version, db):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-laura')}"},
    )
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    clip_id = _make_clip(db, speaker_id, session_id)

    res = client.get(
        f"/api/me/clips/{clip_id}/listen",
        headers={"Authorization": f"Bearer {_token('user-laura')}"},
    )
    assert res.status_code == 200
    assert res.json()["url"]  # exact shape depends on storage backend


def test_cannot_listen_to_someone_elses_clip(client, consent_version, db):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-mona')}"},
    )
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    clip_id = _make_clip(db, speaker_id, session_id)

    res = client.get(
        f"/api/me/clips/{clip_id}/listen",
        headers={"Authorization": f"Bearer {_token('user-someone-else')}"},
    )
    assert res.status_code == 404


def test_edit_own_profile_after_linking(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-nancy')}"},
    )
    res = client.patch(
        f"/api/speakers/{speaker_id}",
        json={"district": "ललितपुर"},
        headers={"Authorization": f"Bearer {_token('user-nancy')}"},
    )
    assert res.status_code == 200
    with SessionLocal() as db:
        assert db.get(Speaker, speaker_id).district == "ललितपुर"


def test_cannot_edit_someone_elses_profile(client, consent_version):
    speaker_id = _signup(
        client,
        consent_version,
        headers={"Authorization": f"Bearer {_token('user-oscar')}"},
    )
    res = client.patch(
        f"/api/speakers/{speaker_id}",
        json={"district": "hijacked"},
        headers={"Authorization": f"Bearer {_token('user-someone-else')}"},
    )
    assert res.status_code == 403


def test_anonymous_speaker_can_still_be_patched_without_auth(client, consent_version):
    """A speaker with no linked account (only possible now as a legacy row,
    from before signing in became mandatory) must stay PATCH-able so it isn't
    stranded."""
    with SessionLocal() as db:
        speaker_id = _make_legacy_anonymous_speaker(db, consent_version)
    res = client.patch(f"/api/speakers/{speaker_id}", json={"district": "भक्तपुर"})
    assert res.status_code == 200
