from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConsentIn(BaseModel):
    version: str
    accepted: bool
    # Separate opt-in. Asked before recording because it cannot be added later.
    commercial_use: bool = False


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


class SessionIn(BaseModel):
    speaker_id: str
    lang: str = "ne"
    device_hint: str | None = Field(default=None, max_length=300)
    sample_rate: int | None = None


class SessionOut(BaseModel):
    session_id: str
    lang: str


class PromptOut(BaseModel):
    id: str
    text: str
    lang: str
    category: str | None = None


class ClipInitIn(BaseModel):
    session_id: str
    prompt_id: str


class UploadTarget(BaseModel):
    url: str
    method: str
    headers: dict[str, str]


class ClipInitOut(BaseModel):
    clip_id: str
    object_key: str
    upload: UploadTarget


class ClipCompleteIn(BaseModel):
    # Client metrics are a UX convenience only; the server re-measures.
    client_metrics: dict | None = None


class QCOut(BaseModel):
    clip_id: str
    passed: bool
    codes: list[str]
    reasons: list[str]
    warnings: list[str]
    duration_s: float
    sample_rate: int
    snr_db: float
    peak_dbfs: float
    rms_dbfs: float
    noise_floor_dbfs: float
    clipping_ratio: float
    lead_silence_ms: float
    trail_silence_ms: float


class ProgressOut(BaseModel):
    speaker_id: str
    session_id: str
    recorded: int
    passed: int
    failed: int
    remaining: int


class SpokenConsentInitOut(BaseModel):
    object_key: str
    upload: UploadTarget
