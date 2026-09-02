"""One sitting by one speaker."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import new_ulid
from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.clip import Clip
    from app.models.speaker import Speaker


class RecordingSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"), index=True)
    lang: Mapped[str] = mapped_column(String(16), default="ne")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Device hints help explain a batch of bad takes. No IP, no user id.
    device_hint: Mapped[str | None] = mapped_column(String(300))
    sample_rate: Mapped[int | None] = mapped_column(Integer)

    speaker: Mapped["Speaker"] = relationship(back_populates="sessions")
    clips: Mapped[list["Clip"]] = relationship(back_populates="session")
