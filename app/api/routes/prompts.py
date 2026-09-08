"""Serving the next sentences to read."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
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

    # How many speakers, across the whole corpus, have already successfully
    # read each prompt. Preferring the least-covered ones spreads recordings
    # evenly across the pool instead of leaving it to chance -- pure random
    # selection can easily let some sentences pile up hundreds of takes while
    # others never get picked at all.
    served_count = (
        select(Clip.prompt_id, func.count().label("served"))
        .where(Clip.qc_status == "passed", Clip.tombstoned.is_(False))
        .group_by(Clip.prompt_id)
        .subquery()
    )

    prompts = db.scalars(
        select(Prompt)
        .outerjoin(served_count, served_count.c.prompt_id == Prompt.id)
        .where(
            Prompt.lang == session.lang,
            Prompt.active.is_(True),
            Prompt.id.not_in(already),
        )
        # Least-served first; random only breaks ties, so it never overrides
        # coverage the way pure ORDER BY random() could.
        .order_by(func.coalesce(served_count.c.served, 0).asc(), func.random())
        .limit(limit)
    ).all()
    return [
        schemas.PromptOut(id=p.id, text=p.text, lang=p.lang, category=p.category)
        for p in prompts
    ]
