"""Speaker registration and consent capture."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import current_user, current_user_optional, get_db
from app.core.accounts import AuthUser
from app.core.config import get_settings
from app.core.ids import new_ulid
from app.models import ConsentRecord, Speaker
from app.services.consent import consent_sha256

logger = logging.getLogger("voice")
router = APIRouter()


@router.post("/api/speakers", response_model=schemas.SpeakerOut, status_code=201)
def create_speaker(
    payload: schemas.SpeakerIn,
    db: Session = Depends(get_db),
    user: AuthUser | None = Depends(current_user_optional),
):
    settings = get_settings()

    if not payload.consent.accepted:
        raise HTTPException(400, "सहमति नदिई रेकर्ड गर्न मिल्दैन। (consent required)")
    if payload.consent.version != settings.consent_version:
        raise HTTPException(
            409,
            "सहमति पाठ अद्यावधिक भएको छ — पृष्ठ पुनः लोड गर्नुहोस्। (consent version stale)",
        )
    if not payload.consent.commercial_use:
        raise HTTPException(
            400,
            "व्यावसायिक अधिकार हस्तान्तरण सहमति आवश्यक छ। (commercial consent required)",
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
        user_id=user.id if user else None,
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


@router.patch("/api/speakers/{speaker_id}")
def update_speaker(
    speaker_id: str,
    payload: schemas.SpeakerUpdate,
    db: Session = Depends(get_db),
    user: AuthUser | None = Depends(current_user_optional),
):
    """Fill in profile details after recording, or edit them later.

    The speaker row (and its consent) already exists -- it was created right
    after the consent step, before recording started, so clips have a speaker
    to belong to from the first upload. This just completes the profile.

    No auth is required while the speaker has no linked account (the normal
    save-after-recording step may happen before anyone signs in) -- but once
    linked, only that account may edit it. The profile page uses this same
    endpoint for real edits, so that path has to be protected.
    """
    speaker = db.get(Speaker, speaker_id)
    if speaker is None:
        raise HTTPException(404, "speaker not found")
    if speaker.user_id is not None and (user is None or user.id != speaker.user_id):
        raise HTTPException(403, "not your profile")

    for field, value in payload.model_dump().items():
        setattr(speaker, field, value)
    db.commit()

    logger.info("speaker profile completed id=%s", speaker.id)
    return {"speaker_id": speaker.id}


@router.post("/api/speakers/{speaker_id}/link-account")
def link_speaker_to_account(
    speaker_id: str,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Attach an account to a speaker created before that account existed.

    Recording never requires signing in first, so the common path is:
    consent -> anonymous speaker created -> partway through, the contributor
    signs in (or signs up) to make sure their work is saved. Account linking
    at creation time alone misses exactly that case -- this is what the
    frontend calls the moment a session becomes signed-in, so it isn't.

    Idempotent for the same account (calling it again is harmless); refuses
    to hand an already-linked speaker to a *different* account.
    """
    speaker = db.get(Speaker, speaker_id)
    if speaker is None:
        raise HTTPException(404, "speaker not found")
    if speaker.user_id is not None and speaker.user_id != user.id:
        raise HTTPException(409, "speaker is already linked to a different account")

    speaker.user_id = user.id
    db.commit()
    return {"speaker_id": speaker.id, "linked": True}
