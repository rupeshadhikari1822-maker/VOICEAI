"""Speaker registration and consent capture."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.ids import new_ulid
from app.models import ConsentRecord, Speaker
from app.services.consent import consent_sha256

logger = logging.getLogger("voice")
router = APIRouter()


@router.post("/api/speakers", response_model=schemas.SpeakerOut, status_code=201)
def create_speaker(payload: schemas.SpeakerIn, db: Session = Depends(get_db)):
    settings = get_settings()

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
