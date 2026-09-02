"""Serving the next sentences to read."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import get_db
from app.models import Clip, Prompt, RecordingSession

router = APIRouter()


@router.get("/api/prompts", response_model=list[schemas.PromptOut])
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
