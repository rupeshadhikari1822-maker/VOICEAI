"""Staff dashboard: corpus health at a glance.

Same trust boundary as /review -- a reviewer token, not a Supabase account.
This is operational visibility (how much has been recorded, how healthy is
it, who's contributing), not a place to edit anything; actual QC decisions
still happen in /review.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.api.deps import current_reviewer, get_db, pagination
from app.core.admin_auth import verify_password
from app.core.config import get_settings
from app.core.security import ReviewAuthError, extract_token, reviewer_for_token
from app.models import Clip, Prompt, RecordingSession, Speaker
from app.schemas.admin import AdminLoginIn, AdminLoginOut
from app.services.export import ExportEmpty, export_to_zip
from app.services.storage import get_storage

router = APIRouter()


@router.get("/admin/login", include_in_schema=False)
def admin_login_page() -> FileResponse:
    """Public on purpose -- this is what hands out the reviewer token
    /admin itself still requires."""
    return FileResponse(get_settings().base_dir / "static" / "admin" / "login.html")


@router.post("/api/admin/login", include_in_schema=False)
def admin_login(payload: AdminLoginIn) -> AdminLoginOut:
    settings = get_settings()

    misconfigured = not settings.admin_email or not settings.admin_password_hash
    email_matches = (
        not misconfigured
        and payload.email.strip().lower() == settings.admin_email.strip().lower()  # type: ignore[union-attr]
    )
    password_matches = not misconfigured and verify_password(
        payload.password, settings.admin_password_hash  # type: ignore[arg-type]
    )
    if misconfigured or not email_matches or not password_matches:
        raise HTTPException(401, "Incorrect email or password.")

    token = settings.reviewers.get("admin")
    if not token:
        raise HTTPException(
            500,
            "Admin login is enabled but REVIEWER_TOKENS has no entry named "
            "'admin' -- set REVIEWER_TOKENS=admin:<token> too.",
        )
    return AdminLoginOut(token=token, reviewer="admin")


@router.get("/admin", include_in_schema=False, response_model=None)
def admin_page(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> FileResponse | RedirectResponse:
    """A human opens this directly in a browser, unlike the JSON routes below
    (which stay a bare 401) -- missing or wrong auth sends them to the login
    page instead of a raw error."""
    try:
        reviewer_for_token(extract_token(authorization, token))
    except ReviewAuthError:
        return RedirectResponse("/admin/login")
    return FileResponse(get_settings().base_dir / "static" / "admin" / "index.html")


@router.get("/api/admin/overview")
def admin_overview(
    _reviewer: str = Depends(current_reviewer), db: Session = Depends(get_db)
) -> dict:
    total_speakers = db.scalar(select(func.count()).select_from(Speaker)) or 0
    withdrawn_speakers = (
        db.scalar(
            select(func.count())
            .select_from(Speaker)
            .where(Speaker.withdrawn_at.is_not(None))
        )
        or 0
    )
    linked_speakers = (
        db.scalar(
            select(func.count())
            .select_from(Speaker)
            .where(Speaker.user_id.is_not(None))
        )
        or 0
    )
    total_sessions = db.scalar(select(func.count()).select_from(RecordingSession)) or 0

    clip_counts = dict(
        db.execute(
            select(Clip.qc_status, func.count())
            .where(Clip.tombstoned.is_(False))
            .group_by(Clip.qc_status)
        ).all()
    )

    total_prompts = db.scalar(select(func.count()).select_from(Prompt)) or 0
    active_prompts = (
        db.scalar(select(func.count()).select_from(Prompt).where(Prompt.active.is_(True)))
        or 0
    )

    # Active prompts nobody has successfully read yet -- the corpus's actual
    # coverage gap, not just "how many prompts exist".
    served = select(Clip.prompt_id).where(
        Clip.qc_status == "passed", Clip.tombstoned.is_(False)
    )
    uncovered_prompts = (
        db.scalar(
            select(func.count())
            .select_from(Prompt)
            .where(Prompt.active.is_(True), Prompt.id.not_in(served))
        )
        or 0
    )

    avg_snr = db.scalar(select(func.avg(Clip.snr_db)).where(Clip.qc_status == "passed"))
    pending_review = (
        db.scalar(
            select(func.count())
            .select_from(Clip)
            .where(
                Clip.qc_status == "passed",
                Clip.verify_status == "unverified",
                Clip.tombstoned.is_(False),
            )
        )
        or 0
    )

    return {
        "speakers": {
            "total": total_speakers,
            "withdrawn": withdrawn_speakers,
            "linked_to_account": linked_speakers,
        },
        "sessions": {"total": total_sessions},
        "clips": {
            "passed": clip_counts.get("passed", 0),
            "failed": clip_counts.get("failed", 0),
            "pending": clip_counts.get("pending", 0),
            "total": sum(clip_counts.values()),
        },
        "prompts": {
            "total": total_prompts,
            "active": active_prompts,
            "inactive_pending_review": total_prompts - active_prompts,
            "active_uncovered": uncovered_prompts,
        },
        "quality": {"avg_snr_db": round(avg_snr, 1) if avg_snr is not None else None},
        "review": {"pending": pending_review},
    }


@router.get("/api/admin/speakers")
def admin_speakers(
    _reviewer: str = Depends(current_reviewer),
    db: Session = Depends(get_db),
    page: dict = Depends(pagination),
) -> dict:
    total = db.scalar(select(func.count()).select_from(Speaker)) or 0

    passed_counts = (
        select(Clip.speaker_id, func.count().label("passed"))
        .where(Clip.qc_status == "passed", Clip.tombstoned.is_(False))
        .group_by(Clip.speaker_id)
        .subquery()
    )
    rows = db.execute(
        select(Speaker, func.coalesce(passed_counts.c.passed, 0))
        .outerjoin(passed_counts, passed_counts.c.speaker_id == Speaker.id)
        .order_by(Speaker.created_at.desc())
        .limit(page["limit"])
        .offset(page["offset"])
    ).all()

    return {
        "total": total,
        "speakers": [
            {
                "speaker_id": s.id,
                "created_at": s.created_at.isoformat(),
                "name": s.name,
                "email": s.email,
                "phone": s.phone,
                "province": s.province,
                "mother_tongue": s.mother_tongue,
                "linked_account": s.user_id is not None,
                "withdrawn": s.is_withdrawn,
                "passed_clips": passed,
            }
            for s, passed in rows
        ],
    }


@router.get("/api/admin/export", include_in_schema=False)
def admin_export(
    _reviewer: str = Depends(current_reviewer),
    db: Session = Depends(get_db),
    format: Literal["asr", "tts", "ljspeech", "hf"] = Query("asr"),
    sr: int | None = Query(None, ge=8000, le=48000),
    lang: str = Query("ne"),
    verified_only: bool = Query(False),
    min_snr: float | None = Query(None),
    limit: int | None = Query(None, ge=1),
) -> FileResponse:
    """A downloadable, training-ready bundle: audio + manifest(s) + a dataset
    card, in whichever shape the target training pipeline expects --

    - `asr`: train/dev/test WAV folders + per-split `manifest.jsonl` (NeMo/
      ESPnet/Whisper-fine-tuning style).
    - `tts`: same, loudness-normalised for TTS training.
    - `ljspeech`: `wavs/` + pipe-delimited `metadata.csv`, the format Tacotron2/
      VITS/Coqui TTS/ESPnet's TTS recipes read natively.
    - `hf`: a Hugging Face `datasets` AudioFolder (`data/{split}/metadata.csv`),
      loadable with `load_dataset("audiofolder", data_dir=...)`.

    Same pipeline as `scripts/export_dataset.py` (`app/services/export/`), so
    the same speaker-disjoint splits and PII fence apply -- this is that
    script, reachable without shell access to the box.
    """
    storage = get_storage()
    try:
        workdir, zip_path, result = export_to_zip(
            db,
            storage,
            fmt=format,
            sr=sr,
            lang=lang,
            verified_only=verified_only,
            min_snr=min_snr,
            limit=limit,
        )
    except ExportEmpty as exc:
        raise HTTPException(404, str(exc)) from exc

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return FileResponse(
        zip_path,
        filename=f"voiceai-{format}-{stamp}.zip",
        media_type="application/zip",
        background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
    )
