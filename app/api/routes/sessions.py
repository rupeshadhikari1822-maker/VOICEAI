"""Recording sessions and per-session progress."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import get_db
from app.core.ids import new_ulid
from app.models import Clip, Prompt, RecordingSession, Speaker

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
