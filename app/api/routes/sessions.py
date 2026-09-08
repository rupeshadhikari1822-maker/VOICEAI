"""Recording sessions and per-session progress."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import get_db
from app.core.ids import new_ulid
from app.models import Clip, Prompt, RecordingSession, Speaker
from app.services.storage import get_storage

logger = logging.getLogger("voice")
router = APIRouter()


@router.post("/api/sessions", response_model=schemas.SessionOut, status_code=201)
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


@router.get(
    "/api/sessions/{session_id}/progress", response_model=schemas.ProgressOut
)
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

    total_active = (
        db.scalar(
            select(func.count())
            .select_from(Prompt)
            .where(Prompt.lang == session.lang, Prompt.active.is_(True))
        )
        or 0
    )
    passed = counts.get("passed", 0)

    return schemas.ProgressOut(
        speaker_id=session.speaker_id,
        session_id=session_id,
        recorded=sum(counts.values()),
        passed=passed,
        failed=counts.get("failed", 0),
        remaining=max(0, total_active - passed),
    )


@router.post("/api/sessions/{session_id}/discard", response_model=schemas.DiscardOut)
def discard_session(session_id: str, db: Session = Depends(get_db)):
    """Cancel this session: throw away every clip sent so far, as if it never
    happened, and close the session out so nothing more gets attached to it.

    Object first, then tombstone -- same order as scripts/withdraw.py, so a
    crash midway never leaves the DB pointing at audio that's already gone.
    Unlike withdraw.py, this never touches the speaker's PII or consent: the
    contributor is starting a new session, not leaving the corpus.
    """
    session = db.get(RecordingSession, session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    clips = db.scalars(
        select(Clip).where(Clip.session_id == session_id, Clip.tombstoned.is_(False))
    ).all()

    storage = get_storage()
    for clip in clips:
        try:
            storage.delete(clip.object_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("discard: could not delete %s: %s", clip.object_key, exc)
        clip.tombstoned = True
        clip.client_metrics = None

    if session.ended_at is None:
        session.ended_at = datetime.now(timezone.utc)

    db.commit()
    return schemas.DiscardOut(discarded=len(clips))
