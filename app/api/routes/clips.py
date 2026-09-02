"""Clip upload and QC.

Three steps, and the split matters:

  1. POST /api/clips/init      reserve a clip row + object key, get a presigned PUT
  2. PUT  <presigned url>      browser sends the WAV straight to the bucket
  3. POST /api/clips/{id}/complete
                               server reads the stored bytes back and runs QC

Step 2 never touches this process, so the API stays small no matter how much
audio is flowing. Step 3 reads from storage rather than trusting anything the
client said -- `app/services/audio_qc.py` is the authority on pass/fail.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import get_db, get_thresholds
from app.core.config import get_settings
from app.core.ids import new_ulid
from app.models import Clip, Prompt, RecordingSession, Speaker
from app.services.audio_qc import analyze
from app.services.storage import LocalStorage, StorageError, get_storage, raw_key

logger = logging.getLogger("voice")
router = APIRouter()


@router.post("/api/clips/init", response_model=schemas.ClipInitOut, status_code=201)
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


@router.post("/api/clips/{clip_id}/complete", response_model=schemas.QCOut)
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
    result = analyze(data, get_thresholds())

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


@router.put("/api/_local_upload", include_in_schema=False)
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
    if len(body) > get_settings().max_clip_bytes:
        raise HTTPException(413, "clip too large")

    storage.put_bytes(key, body)
    return JSONResponse({"ok": True, "bytes": len(body)})


@router.get("/api/_local_download", include_in_schema=False)
def local_download(
    key: str = Query(...),
    expires: int = Query(...),
    sig: str = Query(...),
):
    """Stands in for a presigned S3 GET when STORAGE_BACKEND=local.

    Used by the review UI for playback. On S3 the browser fetches the bucket
    directly and this route is never reached.
    """
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(404, "not found")
    if not storage.verify(key, expires, sig):
        raise HTTPException(403, "invalid or expired download signature")

    try:
        path = storage.local_path(key)
    except StorageError:
        raise HTTPException(400, "unsafe object key")
    if not path.is_file():
        raise HTTPException(404, "object not found")

    return FileResponse(path, media_type="audio/wav")
