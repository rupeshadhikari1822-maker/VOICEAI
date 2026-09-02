"""Spoken consent upload.

Kept apart from the corpus under `consent/`, so an export can never sweep it up
by accident.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.api.deps import get_db
from app.core.config import get_settings
from app.models import ConsentRecord, Speaker
from app.services.storage import consent_key, get_storage

router = APIRouter()


@router.post(
    "/api/consent/spoken/init", response_model=schemas.SpokenConsentInitOut
)
def spoken_consent_init(speaker_id: str = Query(...), db: Session = Depends(get_db)):
    speaker = db.get(Speaker, speaker_id)
    if speaker is None or speaker.is_withdrawn:
        raise HTTPException(404, "speaker not found")

    key = consent_key(speaker.id, get_settings().consent_version)
    target = get_storage().presign_put(key)
    return schemas.SpokenConsentInitOut(
        object_key=key,
        upload=schemas.UploadTarget(
            url=target.url, method=target.method, headers=target.headers
        ),
    )


@router.post("/api/consent/spoken/complete")
def spoken_consent_complete(
    speaker_id: str = Query(...), db: Session = Depends(get_db)
):
    record = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.speaker_id == speaker_id)
        .order_by(ConsentRecord.accepted_at.desc())
        .limit(1)
    ).first()
    if record is None:
        raise HTTPException(404, "consent record not found")

    key = consent_key(speaker_id, get_settings().consent_version)
    if not get_storage().exists(key):
        raise HTTPException(409, "spoken consent upload not found")

    record.spoken_clip_key = key
    db.commit()
    return {"ok": True, "object_key": key}
