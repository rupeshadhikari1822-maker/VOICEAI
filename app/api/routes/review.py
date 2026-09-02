"""The validation pass.

One design decision runs through this whole module: **the reviewer is not shown
QC metrics or the ASR transcript until after they commit a verdict.**

Showing "SNR 42 dB" beside the play button anchors them into passing it; showing
the ASR text means they review the transcript rather than the audio, and quietly
inherit whatever the model got wrong. Both are available immediately afterwards,
in the verdict response, which is where they are useful -- for auditing a
decision rather than making it.

Audio is served by short-lived presigned URL, never streamed through this
process.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import current_reviewer, get_db
from app.core.config import get_settings
from app.models import Clip
from app.schemas.review import (
    ReasonOut,
    ReviewClipOut,
    ReviewStatsOut,
    UndoOut,
    VerdictIn,
    VerdictOut,
)
from app.services.review import (
    VerdictError,
    keyboard_map,
    next_batch,
    record_verdict,
    undo_last,
)
from app.services.review.stats import TOO_FAST_MS, collect
from app.services.storage import get_storage

router = APIRouter()


@router.get("/review", include_in_schema=False)
def review_page(_reviewer: str = Depends(current_reviewer)) -> FileResponse:
    return FileResponse(get_settings().base_dir / "static" / "review" / "index.html")


@router.get("/api/review/config")
def review_config(reviewer: str = Depends(current_reviewer)) -> dict:
    settings = get_settings()
    return {
        "reviewer": reviewer,
        "reasons": [ReasonOut(**r).model_dump() for r in keyboard_map()],
        "session_minutes": settings.review_session_minutes,
        "too_fast_ms": TOO_FAST_MS,
    }


@router.get("/api/review/next", response_model=list[ReviewClipOut])
def review_next(
    count: int = Query(10, ge=1, le=50),
    lang: str = Query("ne"),
    reviewer: str = Depends(current_reviewer),
    db: Session = Depends(get_db),
):
    """A batch, so the UI can prefetch audio and the reviewer never waits."""
    settings = get_settings()
    storage = get_storage()
    clips = next_batch(db, settings, lang=lang, count=count)

    out: list[ReviewClipOut] = []
    for clip in clips:
        target = storage.presign_get(clip.object_key, settings.presign_get_ttl_s)
        out.append(
            ReviewClipOut(
                clip_id=clip.id,
                prompt_text=clip.prompt_text,
                lang=clip.lang,
                duration_s=clip.duration_s,
                audio_url=target.url,
                audio_expires_at=target.expires_at,
            )
        )
    return out


@router.post("/api/review/{clip_id}/verdict", response_model=VerdictOut)
def review_verdict(
    clip_id: str,
    payload: VerdictIn,
    reviewer: str = Depends(current_reviewer),
    db: Session = Depends(get_db),
):
    clip = db.get(Clip, clip_id)
    if clip is None or clip.tombstoned:
        raise HTTPException(404, "clip not found")

    try:
        record_verdict(
            db,
            clip,
            reviewer=reviewer,
            action=payload.action,
            reason=payload.reason,
            notes=payload.notes,
            time_spent_ms=payload.time_spent_ms,
        )
    except VerdictError as exc:
        raise HTTPException(400, str(exc))

    db.commit()

    # Only now: what the model heard and what the meters said.
    return VerdictOut(
        clip_id=clip.id,
        verify_status=clip.verify_status,
        reviewer=reviewer,
        asr_text=clip.asr_text,
        asr_cer=clip.asr_cer,
        snr_db=clip.snr_db,
        peak_dbfs=clip.peak_dbfs,
    )


@router.post("/api/review/undo", response_model=UndoOut)
def review_undo(
    reviewer: str = Depends(current_reviewer), db: Session = Depends(get_db)
):
    clip = undo_last(db, reviewer)
    if clip is None:
        return UndoOut(undone=False)
    db.commit()
    return UndoOut(undone=True, clip_id=clip.id, verify_status=clip.verify_status)


@router.get("/api/review/stats", response_model=ReviewStatsOut)
def review_stats(
    lang: str = Query("ne"),
    reviewer: str = Depends(current_reviewer),
    db: Session = Depends(get_db),
):
    """Throughput and quality. Aggregation lives in services/review/stats.py."""
    s = collect(db, reviewer=reviewer, lang=lang)
    return ReviewStatsOut(reviewer=reviewer, **vars(s))
