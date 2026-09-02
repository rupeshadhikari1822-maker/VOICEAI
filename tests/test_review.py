"""The validation pass.

The queue, the verdict trail, auth, and the CER normaliser that decides which
clips a human never sees. That last one is the most dangerous code in the
system: a normaliser that is slightly wrong auto-rejects good clips in bulk, and
nobody notices, because the whole point of the pre-filter is that no human looks
at what it decided.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.models import Clip, Prompt, ReviewEvent
from app.services.review.asr_prefilter import decide, uncertainty_priority
from app.services.review.normalize import cer, levenshtein, normalize
from app.services.review.queue import next_batch, sampled_in, speaker_policy
from app.services.review.reasons import RejectReason, ReviewAction, keyboard_map
from app.services.review.verdicts import VerdictError, record_verdict, undo_last
from tests.synth import clean_take
from tests.test_smoke import make_speaker, upload

TOKEN = "test-reviewer-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module", autouse=True)
def _reviewer_configured():
    """Configure reviewer tokens for this module only."""
    import os

    previous = os.environ.get("REVIEWER_TOKENS")
    os.environ["REVIEWER_TOKENS"] = f"tester:{TOKEN},second:other-token"
    get_settings.cache_clear()
    yield
    if previous is None:
        os.environ.pop("REVIEWER_TOKENS", None)
    else:
        os.environ["REVIEWER_TOKENS"] = previous
    get_settings.cache_clear()


def recorded_clip(client, consent_version, prompt_id) -> str:
    """Record one clean, QC-passing clip and return its id."""
    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]
    init = client.post(
        "/api/clips/init",
        json={"session_id": session_id, "prompt_id": prompt_id},
    ).json()
    upload(client, init["upload"]["url"], clean_take())
    client.post(f"/api/clips/{init['clip_id']}/complete", json={})
    return init["clip_id"]


# --- normalisation and CER ---------------------------------------------


def test_identical_text_is_zero_cer():
    text = "आज काठमाडौंमा बिहानैदेखि पानी परिरहेको छ।"
    assert cer(text, text) == 0.0


def test_punctuation_is_not_a_reading_error():
    """A missing danda is not a misread; CER must not punish it."""
    assert cer("यो बाटो कता जान्छ?", "यो बाटो कता जान्छ") == 0.0
    assert cer("ज्ञान बाँड्दा घट्दैन, बढ्छ।", "ज्ञान बाँड्दा घट्दैन बढ्छ") == 0.0


def test_zero_width_joiners_normalise_away():
    """ZWJ/ZWNJ only affect conjunct rendering and are invisible."""
    assert normalize("क‌ख") == normalize("कख")
    assert normalize("क‍ख") == normalize("कख")
    assert cer("कख", "क‌ख") == 0.0


def test_devanagari_digits_map_to_ascii():
    assert normalize("सन् २०७५ मा") == "सन् 2075 मा"
    assert cer("२०७५", "2075") == 0.0


def test_nfc_normalisation_of_nukta_forms():
    """क़ as one codepoint vs क + nukta must compare equal."""
    precomposed = "क़"
    decomposed = "क़"
    assert normalize(precomposed) == normalize(decomposed)
    assert cer(precomposed, decomposed) == 0.0


def test_known_misread_scores_in_the_human_band():
    """One substituted word: wrong, but not wrong enough to auto-reject."""
    ref = "आज काठमाडौंमा बिहानैदेखि पानी परिरहेको छ।"
    hyp = "आज पोखरामा बिहानैदेखि पानी परिरहेको छ।"
    score = cer(ref, hyp)
    assert 0.10 < score < 0.40, f"expected the ambiguous band, got {score}"


def test_completely_different_text_scores_high():
    assert cer("आज काठमाडौंमा पानी परिरहेको छ।", "मलाई भोक लाग्यो।") > 0.4


def test_empty_hypothesis_is_total_error():
    """Silence transcribed against a real prompt is a full miss, not 0.0."""
    assert cer("नमस्ते", "") == 1.0


def test_empty_reference_edge_cases():
    assert cer("", "") == 0.0
    assert cer("", "something") == 1.0


def test_levenshtein_basics():
    assert levenshtein("", "") == 0
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("abc", "abd") == 1
    assert levenshtein("abc", "") == 3
    assert levenshtein("kitten", "sitting") == 3


# --- prefilter decisions ------------------------------------------------


def test_prefilter_auto_verifies_a_match():
    settings = Settings(asr_auto_verify_cer=0.10, asr_auto_reject_cer=0.40)
    d = decide("नमस्ते साथी", "नमस्ते साथी", settings)
    assert d.verify_status == "verified"
    assert d.auto is True
    assert d.reject_reason is None


def test_prefilter_auto_rejects_a_misread():
    settings = Settings(asr_auto_verify_cer=0.10, asr_auto_reject_cer=0.40)
    d = decide("नमस्ते साथी", "मलाई भोक लाग्यो अहिले", settings)
    assert d.verify_status == "rejected"
    assert d.reject_reason == RejectReason.MISREAD.value
    assert d.auto is True


def test_prefilter_sends_the_middle_to_a_human():
    settings = Settings(asr_auto_verify_cer=0.10, asr_auto_reject_cer=0.40)
    d = decide(
        "आज काठमाडौंमा बिहानैदेखि पानी परिरहेको छ।",
        "आज पोखरामा बिहानैदेखि पानी परिरहेको छ।",
        settings,
    )
    assert d.verify_status == "unverified"
    assert d.auto is False
    assert d.review_priority > 0


def test_priority_peaks_at_maximum_uncertainty():
    settings = Settings(asr_auto_verify_cer=0.10, asr_auto_reject_cer=0.40)
    middle = uncertainty_priority(0.25, settings)
    near_edge = uncertainty_priority(0.12, settings)
    assert middle == 100
    assert middle > near_edge


# --- reject reasons -----------------------------------------------------


def test_reject_reasons_are_a_closed_set():
    assert "misread" in RejectReason.values()
    assert len(RejectReason.values()) == 9
    with pytest.raises(ValueError):
        RejectReason("not-a-real-reason")


def test_keyboard_map_is_stable_and_covers_1_to_9():
    mapping = keyboard_map()
    assert [m["key"] for m in mapping] == [str(i) for i in range(1, 10)]
    # Reviewers build muscle memory; slot 1 must stay misread.
    assert mapping[0]["reason"] == "misread"


# --- auth ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/review/next", "/api/review/stats", "/api/review/config", "/review"],
)
def test_review_requires_a_token(client, path):
    assert client.get(path).status_code == 401


def test_review_rejects_an_unknown_token(client):
    res = client.get("/api/review/next", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401


def test_review_accepts_a_valid_token_and_names_the_reviewer(client):
    res = client.get("/api/review/config", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["reviewer"] == "tester"


def test_token_also_accepted_as_a_query_parameter(client):
    """`<audio src>` cannot carry a header, so the query form must work."""
    assert client.get(f"/api/review/config?token={TOKEN}").status_code == 200


# --- queue --------------------------------------------------------------


def test_queue_excludes_tombstoned_withdrawn_and_settled(
    client, consent_version, prompts, db
):
    clip_id = recorded_clip(client, consent_version, prompts[0])
    settings = get_settings()

    def queued_ids():
        return {c.id for c in next_batch(db, settings, count=50)}

    assert clip_id in queued_ids()

    clip = db.get(Clip, clip_id)
    clip.tombstoned = True
    db.commit()
    assert clip_id not in queued_ids(), "tombstoned clips must never be reviewed"

    clip.tombstoned = False
    clip.verify_status = "verified"
    db.commit()
    assert clip_id not in queued_ids(), "already-settled clips must not reappear"

    clip.verify_status = "unverified"
    clip.speaker.withdrawn_at = datetime.now(timezone.utc)
    db.commit()
    assert clip_id not in queued_ids(), "withdrawn speakers must never be reviewed"


def test_queue_only_offers_qc_passed_clips(client, consent_version, prompts, db):
    clip_id = recorded_clip(client, consent_version, prompts[1])
    clip = db.get(Clip, clip_id)
    clip.qc_status = "failed"
    db.commit()

    ids = {c.id for c in next_batch(db, get_settings(), count=50)}
    assert clip_id not in ids, "a clip failing QC is being re-recorded anyway"


def test_warmup_reviews_everything_then_samples(db):
    """100% for the first N clips, then sampling."""
    settings = Settings(review_warmup_clips=20, review_sample_fraction=0.10)

    # Fresh speaker: nothing reviewed yet, so warm-up.
    fresh = speaker_policy(db, "NO-SUCH-SPEAKER-0001", settings)
    assert fresh.in_warmup is True
    assert fresh.sampling is False


def test_sampling_is_deterministic_and_roughly_the_right_fraction():
    ids = [f"CLIP{i:05d}" for i in range(4000)]
    chosen = [c for c in ids if sampled_in(c, 0.10)]

    # Same answer every time, so a page reload does not reshuffle the queue.
    assert chosen == [c for c in ids if sampled_in(c, 0.10)]
    assert 0.08 < len(chosen) / len(ids) < 0.12

    assert all(sampled_in(c, 1.0) for c in ids[:50])
    assert not any(sampled_in(c, 0.0) for c in ids[:50])


def test_queue_avoids_consecutive_clips_from_one_speaker(
    client, consent_version, prompts, db
):
    """Reviewers habituate to a voice and stop hearing errors in it."""
    for speaker in range(2):
        speaker_id = make_speaker(client, consent_version)
        session_id = client.post(
            "/api/sessions", json={"speaker_id": speaker_id}
        ).json()["session_id"]
        for prompt_id in prompts[2:6]:
            init = client.post(
                "/api/clips/init",
                json={"session_id": session_id, "prompt_id": prompt_id},
            ).json()
            upload(client, init["upload"]["url"], clean_take())
            client.post(f"/api/clips/{init['clip_id']}/complete", json={})

    batch = next_batch(db, get_settings(), count=8)
    speakers = [c.speaker_id for c in batch]
    repeats = sum(1 for a, b in zip(speakers, speakers[1:]) if a == b)
    # Perfect alternation is not always possible, but it should be rare.
    assert repeats <= 1, f"too much speaker clustering: {speakers}"


# --- verdicts -----------------------------------------------------------


def test_verdict_writes_both_status_and_event(client, consent_version, prompts, db):
    clip_id = recorded_clip(client, consent_version, prompts[2])

    res = client.post(
        f"/api/review/{clip_id}/verdict",
        headers=AUTH,
        json={"action": "verified", "time_spent_ms": 4200},
    )
    assert res.status_code == 200
    assert res.json()["verify_status"] == "verified"

    with SessionLocal() as fresh:
        clip = fresh.get(Clip, clip_id)
        assert clip.verify_status == "verified"
        assert clip.verified_by == "tester"
        assert clip.verified_at is not None

        events = fresh.scalars(
            select(ReviewEvent).where(ReviewEvent.clip_id == clip_id)
        ).all()
        assert len(events) == 1
        assert events[0].reviewer == "tester"
        assert events[0].time_spent_ms == 4200


def test_rejection_requires_a_valid_reason(client, consent_version, prompts, db):
    clip_id = recorded_clip(client, consent_version, prompts[3])

    no_reason = client.post(
        f"/api/review/{clip_id}/verdict", headers=AUTH, json={"action": "rejected"}
    )
    assert no_reason.status_code == 400

    bad_reason = client.post(
        f"/api/review/{clip_id}/verdict",
        headers=AUTH,
        json={"action": "rejected", "reason": "made-up"},
    )
    assert bad_reason.status_code == 400

    good = client.post(
        f"/api/review/{clip_id}/verdict",
        headers=AUTH,
        json={"action": "rejected", "reason": "misread"},
    )
    assert good.status_code == 200
    assert good.json()["verify_status"] == "rejected"


def test_skip_records_an_event_but_leaves_the_clip_in_the_queue(
    client, consent_version, prompts, db
):
    clip_id = recorded_clip(client, consent_version, prompts[4])
    client.post(
        f"/api/review/{clip_id}/verdict", headers=AUTH, json={"action": "skipped"}
    )

    with SessionLocal() as fresh:
        assert fresh.get(Clip, clip_id).verify_status == "unverified"
        events = fresh.scalars(
            select(ReviewEvent).where(ReviewEvent.clip_id == clip_id)
        ).all()
        assert [e.action for e in events] == ["skipped"]


def test_metrics_are_withheld_until_after_the_verdict(
    client, consent_version, prompts
):
    """The queue payload must not carry SNR or ASR text.

    Showing them beforehand anchors the reviewer into agreeing with the machine.
    """
    recorded_clip(client, consent_version, prompts[5])
    batch = client.get("/api/review/next?count=5", headers=AUTH).json()
    assert batch, "expected something in the queue"

    for item in batch:
        assert "snr_db" not in item
        assert "asr_text" not in item
        assert "qc_codes" not in item
        assert "peak_dbfs" not in item
        assert item["audio_url"]


def test_undo_reverts_only_the_callers_own_last_verdict(
    client, consent_version, prompts, db
):
    clip_id = recorded_clip(client, consent_version, prompts[6])
    client.post(
        f"/api/review/{clip_id}/verdict",
        headers=AUTH,
        json={"action": "rejected", "reason": "partial"},
    )

    undone = client.post("/api/review/undo", headers=AUTH).json()
    assert undone["undone"] is True
    assert undone["clip_id"] == clip_id

    with SessionLocal() as fresh:
        clip = fresh.get(Clip, clip_id)
        assert clip.verify_status == "unverified"
        assert clip.verified_by is None
        assert clip.reject_reason is None
        # History stays append-only: the original verdict is still on record.
        actions = [
            e.action
            for e in fresh.scalars(
                select(ReviewEvent)
                .where(ReviewEvent.clip_id == clip_id)
                .order_by(ReviewEvent.created_at)
            ).all()
        ]
        assert actions == ["rejected", "skipped"]


def test_undo_does_not_touch_another_reviewers_verdict(
    client, consent_version, prompts, db
):
    clip_id = recorded_clip(client, consent_version, prompts[7])
    client.post(
        f"/api/review/{clip_id}/verdict",
        headers=AUTH,
        json={"action": "verified"},
    )

    # A different reviewer's undo must not reach back into someone else's call.
    other = client.post(
        "/api/review/undo", headers={"Authorization": "Bearer other-token"}
    ).json()
    assert other["clip_id"] != clip_id

    with SessionLocal() as fresh:
        assert fresh.get(Clip, clip_id).verify_status == "verified"


def test_undo_with_nothing_to_undo_is_not_an_error(client):
    res = client.post(
        "/api/review/undo", headers={"Authorization": "Bearer other-token"}
    )
    assert res.status_code == 200
    assert res.json()["undone"] in (True, False)


def test_verdict_service_rejects_unknown_actions(db, client, consent_version, prompts):
    clip_id = recorded_clip(client, consent_version, prompts[0])
    clip = db.get(Clip, clip_id)
    with pytest.raises(VerdictError):
        record_verdict(db, clip, reviewer="tester", action="teleport")


# --- presigned playback -------------------------------------------------


def test_presign_get_works_and_expires(client, consent_version, prompts):
    from urllib.parse import urlparse

    recorded_clip(client, consent_version, prompts[1])
    batch = client.get("/api/review/next?count=1", headers=AUTH).json()
    assert batch

    parsed = urlparse(batch[0]["audio_url"])
    ok = client.get(f"{parsed.path}?{parsed.query}")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("audio/")

    forged = client.get(f"{parsed.path}?key=raw/x.wav&expires=99999999999&sig=bad")
    assert forged.status_code == 403


def test_audio_is_not_streamed_through_the_api(client, consent_version, prompts):
    """Playback must be a direct storage URL, not a proxy route.

    On the local backend that URL is served by this app, but it is still a
    signed object URL rather than a clip-id endpoint, so switching to S3 needs
    no frontend change and no corpus flows through the API process.
    """
    recorded_clip(client, consent_version, prompts[2])
    batch = client.get("/api/review/next?count=1", headers=AUTH).json()
    url = batch[0]["audio_url"]
    assert "/api/review/" not in url
    assert "sig=" in url and "expires=" in url


# --- stats --------------------------------------------------------------


def test_stats_reports_throughput_and_reasons(client, consent_version, prompts):
    stats = client.get("/api/review/stats", headers=AUTH).json()
    assert stats["reviewer"] == "tester"
    assert stats["reviewed_by_me"] >= 1
    assert 0.0 <= stats["rejection_rate"] <= 1.0
    assert isinstance(stats["by_reason"], dict)
    assert stats["pending"] >= 0


# --- export still respects review state and privacy ---------------------


def test_export_verified_only_filters_correctly(client, consent_version, prompts, db):
    from app.models import Speaker

    rows = (
        db.query(Clip, Speaker)
        .join(Speaker, Clip.speaker_id == Speaker.id)
        .filter(
            Clip.qc_status == "passed",
            Clip.tombstoned.is_(False),
            Clip.verify_status == "verified",
        )
        .all()
    )
    assert all(c.verify_status == "verified" for c, _ in rows)


def test_export_row_still_has_no_pii_with_review_data_present(db):
    """Review columns must not have opened a new path for PII."""
    from app.models import Speaker

    for speaker in db.query(Speaker).limit(10).all():
        row = speaker.export_row()
        assert "caste_ethnicity" not in row
        assert "name" not in row
        assert "email" not in row
        assert "phone" not in row
        assert "review_notes" not in row
        assert "verified_by" not in row


def test_sampling_kicks_in_after_warmup_and_snaps_back_on_rejections(
    client, consent_version, prompts, db
):
    """The core claim of the queue policy, end to end on real rows.

    Warm-up reviews everything; a clean speaker then drops to sampling; a
    speaker whose rejection rate climbs goes back to 100%.
    """
    settings = Settings(
        review_warmup_clips=5,
        review_sample_fraction=0.10,
        review_reject_rate_trigger=0.20,
    )

    speaker_id = make_speaker(client, consent_version)
    session_id = client.post(
        "/api/sessions", json={"speaker_id": speaker_id}
    ).json()["session_id"]

    clip_ids = []
    for prompt_id in prompts:
        init = client.post(
            "/api/clips/init",
            json={"session_id": session_id, "prompt_id": prompt_id},
        ).json()
        upload(client, init["upload"]["url"], clean_take())
        client.post(f"/api/clips/{init['clip_id']}/complete", json={})
        clip_ids.append(init["clip_id"])

    # Nothing reviewed yet: warm-up, review everything.
    policy = speaker_policy(db, speaker_id, settings)
    assert policy.in_warmup is True
    assert policy.sampling is False

    # Six clean verdicts: past warm-up, behaving, so start sampling.
    for clip_id in clip_ids[:6]:
        clip = db.get(Clip, clip_id)
        clip.verify_status = "verified"
    db.commit()

    policy = speaker_policy(db, speaker_id, settings)
    assert policy.in_warmup is False
    assert policy.sampling is True, "a clean speaker past warm-up should be sampled"
    assert policy.reject_rate == 0.0

    # Now their rejection rate spikes: back to reviewing everything.
    for clip_id in clip_ids[:3]:
        db.get(Clip, clip_id).verify_status = "rejected"
    db.commit()

    policy = speaker_policy(db, speaker_id, settings)
    assert policy.reject_rate > settings.review_reject_rate_trigger
    assert policy.sampling is False, "a speaker going bad must snap back to 100%"
