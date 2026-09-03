"""Documentary proof of consent."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import new_ulid
from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.speaker import Speaker


class ConsentRecord(Base):
    """A version stamp, the hash of the exact text shown, and an optional clip.

    Storing `text_sha256` is what makes this evidence rather than a boolean: if
    the wording is ever changed, old records still point at the old hash and the
    change cannot be hidden.
    """

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    speaker_id: Mapped[str] = mapped_column(
        ForeignKey("speakers.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(40))
    text_sha256: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # The current consent is a mandatory commercial assignment; older records
    # preserve the scope that was accepted at their own version.
    commercial_use: Mapped[bool] = mapped_column(Boolean, default=False)
    spoken_clip_key: Mapped[str | None] = mapped_column(String(400))

    speaker: Mapped["Speaker"] = relationship(back_populates="consents")
