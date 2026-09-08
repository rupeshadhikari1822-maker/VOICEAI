"""A signed-in account's own speaker profiles and recordings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.core.accounts import AuthUser
from app.models import Clip, Speaker
from app.services.storage import get_storage

router = APIRouter()


@router.get("/api/me/speakers")
def my_speakers(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Speaker profiles this account created, with a clip count each.

    Recording never requires an account -- this only surfaces profiles a
    contributor chose to link by being signed in when they registered.
    """
    rows = db.execute(
        select(Speaker, func.count(Clip.id))
        .outerjoin(Clip, Clip.speaker_id == Speaker.id)
        .where(Speaker.user_id == user.id)
        .group_by(Speaker.id)
        .order_by(Speaker.created_at.desc())
    ).all()
    return [
        {
            "speaker_id": speaker.id,
            "created_at": speaker.created_at.isoformat(),
            "clip_count": count,
            "withdrawn": speaker.is_withdrawn,
        }
        for speaker, count in rows
    ]


@router.get("/api/me/profile")
def my_profile(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Full profile + recordings for this account's most recent speaker.

    Unlike /api/me/speakers (a lightweight list), this hands back the actual
    editable fields -- it's what the profile page reads, and what it PATCHes
    back to /api/speakers/{id} to save changes.
    """
    speaker = db.scalar(
        select(Speaker)
        .where(Speaker.user_id == user.id)
        .order_by(Speaker.created_at.desc())
    )
    if speaker is None:
        raise HTTPException(404, "no recordings linked to this account yet")

    clips = db.scalars(
        select(Clip)
        .where(Clip.speaker_id == speaker.id, Clip.tombstoned.is_(False))
        .order_by(Clip.created_at.desc())
    ).all()

    return {
        "speaker_id": speaker.id,
        "created_at": speaker.created_at.isoformat(),
        "withdrawn": speaker.is_withdrawn,
        "name": speaker.name,
        "email": speaker.email,
        "phone": speaker.phone,
        "age_band": speaker.age_band,
        "gender": speaker.gender,
        "province": speaker.province,
        "district": speaker.district,
        "municipality": speaker.municipality,
        "ward": speaker.ward,
        "mother_tongue": speaker.mother_tongue,
        "language_variety": speaker.language_variety,
        "education": speaker.education,
        "caste_ethnicity": speaker.caste_ethnicity,
        "clips": [
            {
                "clip_id": c.id,
                "prompt_text": c.prompt_text,
                "qc_status": c.qc_status,
                "created_at": c.created_at.isoformat(),
            }
            for c in clips
        ],
    }


@router.get("/api/me/clips/{clip_id}/listen")
def listen_to_my_clip(
    clip_id: str,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """A short-lived playback URL for one of the caller's own clips.

    Ownership is checked through the clip's speaker, not just its id -- a
    clip id alone says nothing about who it belongs to.
    """
    clip = db.get(Clip, clip_id)
    speaker = db.get(Speaker, clip.speaker_id) if clip else None
    if clip is None or speaker is None or speaker.user_id != user.id:
        # Same 404 either way: don't confirm a clip id exists for someone
        # who doesn't own it.
        raise HTTPException(404, "clip not found")

    target = get_storage().presign_get(clip.object_key)
    return {"url": target.url, "expires_at": target.expires_at}
