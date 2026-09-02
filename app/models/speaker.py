"""The privacy boundary.

`Speaker` is the only table holding directly identifying data, and nothing on it
is ever written into an object key, a filename, a log line or an export.
Everything downstream refers to a speaker by opaque ULID.

`caste_ethnicity` is sensitive personal information under Nepal's Individual
Privacy Act 2075 s.27(2). It is nullable, it is never required, and
`export_row()` -- the only sanctioned way out of this table -- cannot reach it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import new_ulid
from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.clip import Clip
    from app.models.consent import ConsentRecord
    from app.models.session import RecordingSession


class Speaker(Base):
    """A contributor. Holds all PII in the system, and nothing else does."""

    __tablename__ = "speakers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # --- PII. Never exported, never logged, never in an object key. ----
    name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))

    # --- Sensitive personal information (IPA 2075 s.27(2)). Optional. --
    caste_ethnicity: Mapped[str | None] = mapped_column(String(120))

    # --- Non-identifying attributes. These do get exported. ------------
    age_band: Mapped[str | None] = mapped_column(String(20))
    gender: Mapped[str | None] = mapped_column(String(30))
    # Region, not address. Enough for dialect coverage, useless for tracing.
    province: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    municipality: Mapped[str | None] = mapped_column(String(120))
    ward: Mapped[str | None] = mapped_column(String(10))
    mother_tongue: Mapped[str | None] = mapped_column(String(60))
    language_variety: Mapped[str | None] = mapped_column(String(80))
    education: Mapped[str | None] = mapped_column(String(60))

    # --- Withdrawal (scripts/withdraw.py) ------------------------------
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)

    consents: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="speaker", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["RecordingSession"]] = relationship(back_populates="speaker")
    clips: Mapped[list["Clip"]] = relationship(back_populates="speaker")

    @property
    def is_withdrawn(self) -> bool:
        return self.withdrawn_at is not None

    def export_row(self) -> dict:
        """The only speaker fields allowed to leave the system.

        Deliberately a fixed dict rather than a field list with exclusions: an
        allow-list cannot leak a column somebody adds later, a deny-list can.
        """
        return {
            "speaker_id": self.id,
            "age_band": self.age_band,
            "gender": self.gender,
            "province": self.province,
            "district": self.district,
            "mother_tongue": self.mother_tongue,
            "language_variety": self.language_variety,
        }
