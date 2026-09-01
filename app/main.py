"""FastAPI application.

Upload flow, and why it has three steps:

  1. POST /api/clips/init      reserve a clip row + object key, get a presigned PUT
  2. PUT  <presigned url>      browser sends the WAV straight to the bucket
  3. POST /api/clips/{id}/complete
                               server reads the stored bytes back and runs QC

Step 2 never touches this process, so the API stays small no matter how much
audio is flowing. Step 3 reads from storage rather than trusting anything the
client said -- `app/audio_qc.py` is the authority on pass/fail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.audio_qc import QCThresholds, analyze
from app.config import get_settings
from app.consent import consent_payload, consent_sha256
from app.db import create_all, get_db
from app.ids import new_ulid
from app.models import Clip, ConsentRecord, Prompt, RecordingSession, Speaker
from app.storage import (
    LocalStorage,
    StorageError,
    consent_key,
    get_storage,
    raw_key,
)

logger = logging.getLogger("voice")

settings = get_settings()
thresholds = QCThresholds.for_profile(settings.qc_profile)

app = FastAPI(title="voice.cloudfrm.ai", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    create_all()


# --- static recorder UI -------------------------------------------------

_STATIC_DIR = settings.base_dir / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


# --- config -------------------------------------------------------------


@app.get("/api/config")
def api_config() -> dict:
    """Everything the recorder needs to configure itself and gate takes locally."""
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
        "profile": settings.qc_profile,
    }


# --- speakers -----------------------------------------------------------


@app.post("/api/speakers", response_model=schemas.SpeakerOut, status_code=201)
def create_speaker(payload: schemas.SpeakerIn, db: Session = Depends(get_db)):
    if not payload.consent.accepted:
        raise HTTPException(400, "सहमति नदिई रेकर्ड गर्न मिल्दैन। (consent required)")
    if payload.consent.version != settings.consent_version:
        raise HTTPException(
            409,
            "सहमति पाठ अद्यावधिक भएको छ — पृष्ठ पुनः लोड गर्नुहोस्। (consent version stale)",
        )

    speaker = Speaker(
        id=new_ulid(),
        name=payload.name or None,
        email=payload.email or None,
        phone=payload.phone or None,
        caste_ethnicity=payload.caste_ethnicity or None,
        age_band=payload.age_band,
        gender=payload.gender,
        province=payload.province,
        district=payload.district,
        municipality=payload.municipality,
        ward=payload.ward,
        mother_tongue=payload.mother_tongue,
        language_variety=payload.language_variety,
        education=payload.education,
    )
    db.add(speaker)
    db.add(
        ConsentRecord(
            id=new_ulid(),
            speaker_id=speaker.id,
            version=payload.consent.version,
            text_sha256=consent_sha256(),
            commercial_use=payload.consent.commercial_use,
        )
    )
    db.commit()
    # Log the opaque id only. Never the name, email or phone.
    logger.info("speaker registered id=%s", speaker.id)
    return schemas.SpeakerOut(
        speaker_id=speaker.id, consent_version=payload.consent.version
    )


# --- sessions -----------------------------------------------------------


@app.post("/api/sessions", response_model=schemas.SessionOut, status_code=201)
def create_session(payload: schemas.SessionIn, db: Session = Depends(get_db)):
    speaker = db.get(Speaker, payload.speaker_id)
    if speaker is None or speaker.is_withdrawn:
        raise HTTPException(404, "speaker not found")

    session = RecordingSession(
        id=new_ulid(),
        speaker_id=speaker.id,
        lang=payload.lang,
        device_hint=payload.device_hint,
        sample_rate=payload.sample_rate,
    )
    db.add(session)
    db.commit()
    return schemas.SessionOut(session_id=session.id, lang=session.lang)


@app.get("/api/sessions/{session_id}/progress", response_model=schemas.ProgressOut)
def session_progress(session_id: str, db: Session = Depends(get_db)):
    session = db.get(RecordingSession, session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    rows = db.execute(
        select(Clip.qc_status, func.count())
        .where(Clip.session_id == session_id, Clip.tombstoned.is_(False))
        .group_by(Clip.qc_status)
    ).all()
    counts = {status: n for status, n in rows}

    total_active = db.scalar(
        select(func.count()).select_from(Prompt).where(
            Prompt.lang == session.lang, Prompt.active.is_(True)
        )
    ) or 0
    passed = counts.get("passed", 0)

    return schemas.ProgressOut(
        speaker_id=session.speaker_id,
        session_id=session_id,
        recorded=sum(counts.values()),
        passed=passed,
        failed=counts.get("failed", 0),
        remaining=max(0, total_active - passed),
    )


# --- prompts ------------------------------------------------------------


@app.get("/api/prompts", response_model=list[schemas.PromptOut])
def list_prompts(
    session_id: str = Query(...),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Next sentences for this speaker: active, in-language, not yet passed."""
    session = db.get(RecordingSession, session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    already = select(Clip.prompt_id).where(
        Clip.speaker_id == session.speaker_id,
        Clip.qc_status == "passed",
        Clip.tombstoned.is_(False),
    )
    prompts = db.scalars(
        select(Prompt)
        .where(
            Prompt.lang == session.lang,
            Prompt.active.is_(True),
            Prompt.id.not_in(already),
        )
        .order_by(Prompt.id)
        .limit(limit)
    ).all()
    return [
        schemas.PromptOut(id=p.id, text=p.text, lang=p.lang, category=p.category)
        for p in prompts
    ]


# --- clips --------------------------------------------------------------


@app.post("/api/clips/init", response_model=schemas.ClipInitOut, status_code=201)
def clip_init(payload: schemas.ClipInitIn, db: Session = Depends(get_db)):
    session = db.get(RecordingSession, payload.session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    speaker = db.get(Speaker, session.speaker_id)
    if speaker is None or speaker.is_withdrawn:
        raise HTTPException(404, "speaker not found")

    prompt = db.get(Prompt, payload.prompt_id)
    if prompt is None or not prompt.active:
        raise HTTPException(404, "prompt not found or inactive")

    clip_id = new_ulid()
    key = raw_key(session.lang, speaker.id, session.id, clip_id)

    clip = Clip(
        id=clip_id,
        session_id=session.id,
        speaker_id=speaker.id,
        prompt_id=prompt.id,
        prompt_text=prompt.text,
        lang=session.lang,
        object_key=key,
        qc_status="pending",
    )
    db.add(clip)
    db.commit()

    target = get_storage().presign_put(key)
    return schemas.ClipInitOut(
        clip_id=clip_id,
        object_key=key,
        upload=schemas.UploadTarget(
            url=target.url, method=target.method, headers=target.headers
        ),
    )


@app.post("/api/clips/{clip_id}/complete", response_model=schemas.QCOut)
def clip_complete(
    clip_id: str, payload: schemas.ClipCompleteIn, db: Session = Depends(get_db)
):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "clip not found")

    try:
        data = get_storage().get_bytes(clip.object_key)
    except StorageError:
        raise HTTPException(409, "अपलोड पूरा भएको छैन। (upload not found in storage)")

    # Authoritative pass. Client numbers are recorded but never trusted.
    result = analyze(data, thresholds)

    clip.bytes = len(data)
    clip.qc_status = "passed" if result.passed else "failed"
    clip.duration_s = result.duration_s
    clip.sample_rate = result.sample_rate
    clip.channels = result.channels
    clip.bit_depth = result.bit_depth
    clip.snr_db = result.snr_db
    clip.peak_dbfs = result.peak_dbfs
    clip.rms_dbfs = result.rms_dbfs
    clip.noise_floor_dbfs = result.noise_floor_dbfs
    clip.clipping_ratio = result.clipping_ratio
    clip.lead_silence_ms = result.lead_silence_ms
    clip.trail_silence_ms = result.trail_silence_ms
    clip.qc_codes = result.codes
    clip.qc_reasons = result.reasons
    clip.client_metrics = payload.client_metrics
    db.commit()

    logger.info(
        "clip %s %s snr=%.1f peak=%.1f dur=%.2f",
        clip_id,
        clip.qc_status,
        result.snr_db,
        result.peak_dbfs,
        result.duration_s,
    )

    return schemas.QCOut(
        clip_id=clip_id,
        passed=result.passed,
        codes=result.codes,
        reasons=result.reasons,
        warnings=result.warnings,
        duration_s=result.duration_s,
        sample_rate=result.sample_rate,
        snr_db=result.snr_db,
        peak_dbfs=result.peak_dbfs,
        rms_dbfs=result.rms_dbfs,
        noise_floor_dbfs=result.noise_floor_dbfs,
        clipping_ratio=result.clipping_ratio,
        lead_silence_ms=result.lead_silence_ms,
        trail_silence_ms=result.trail_silence_ms,
    )


# --- spoken consent -----------------------------------------------------


@app.post("/api/consent/spoken/init", response_model=schemas.SpokenConsentInitOut)
def spoken_consent_init(speaker_id: str = Query(...), db: Session = Depends(get_db)):
    speaker = db.get(Speaker, speaker_id)
    if speaker is None or speaker.is_withdrawn:
        raise HTTPException(404, "speaker not found")

    key = consent_key(speaker.id, settings.consent_version)
    target = get_storage().presign_put(key)
    return schemas.SpokenConsentInitOut(
        object_key=key,
        upload=schemas.UploadTarget(
            url=target.url, method=target.method, headers=target.headers
        ),
    )


@app.post("/api/consent/spoken/complete")
def spoken_consent_complete(speaker_id: str = Query(...), db: Session = Depends(get_db)):
    record = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.speaker_id == speaker_id)
        .order_by(ConsentRecord.accepted_at.desc())
        .limit(1)
    ).first()
    if record is None:
        raise HTTPException(404, "consent record not found")

    key = consent_key(speaker_id, settings.consent_version)
    if not get_storage().exists(key):
        raise HTTPException(409, "spoken consent upload not found")

    record.spoken_clip_key = key
    db.commit()
    return {"ok": True, "object_key": key}


# --- local-backend upload sink -----------------------------------------


@app.put("/api/_local_upload", include_in_schema=False)
async def local_upload(
    request: Request,
    key: str = Query(...),
    expires: int = Query(...),
    sig: str = Query(...),
):
    """Stands in for a presigned S3 PUT when STORAGE_BACKEND=local."""
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(404, "not found")
    if not storage.verify(key, expires, sig):
        raise HTTPException(403, "invalid or expired upload signature")

    body = await request.body()
    if not body:
        raise HTTPException(400, "empty body")
    if len(body) > settings.max_clip_bytes:
        raise HTTPException(413, "clip too large")

    storage.put_bytes(key, body)
    return JSONResponse({"ok": True, "bytes": len(body)})


@app.exception_handler(StorageError)
async def _storage_error_handler(_request: Request, exc: StorageError):
    logger.error("storage error: %s", exc)
    return JSONResponse({"detail": "storage error"}, status_code=502)
