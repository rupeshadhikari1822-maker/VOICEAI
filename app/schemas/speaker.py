from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.consent import ConsentIn


class SpeakerIn(BaseModel):
    """Contributor profile.

    Note what is absent: no street address. Province/district/municipality/ward
    gives the dialect-region signal the corpus needs; a house number would add
    liability and nothing else.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)

    age_band: str | None = Field(default=None, max_length=20)
    gender: str | None = Field(default=None, max_length=30)
    province: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    municipality: str | None = Field(default=None, max_length=120)
    ward: str | None = Field(default=None, max_length=10)
    mother_tongue: str | None = Field(default=None, max_length=60)
    language_variety: str | None = Field(default=None, max_length=80)
    education: str | None = Field(default=None, max_length=60)

    # Sensitive personal information, IPA 2075 s.27(2). Optional by design;
    # the UI offers an explicit "prefer not to say".
    caste_ethnicity: str | None = Field(default=None, max_length=120)

    consent: ConsentIn


class SpeakerOut(BaseModel):
    speaker_id: str
    consent_version: str
