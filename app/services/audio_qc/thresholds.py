"""The QC gate's numbers, in one place.

Split from the measurement code because these are policy, not physics. They get
tuned per corpus and per language; the measurements do not.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QCThresholds:
    """Pass/fail gate. `ideal_*` bounds only raise warnings."""

    min_sample_rate: int = 32000
    target_sample_rate: int = 48000

    min_duration_s: float = 1.0
    max_duration_s: float = 20.0
    ideal_min_duration_s: float = 2.0
    ideal_max_duration_s: float = 15.0

    min_snr_db: float = 30.0

    # Hard bounds. Outside these the take is unusable.
    min_peak_dbfs: float = -30.0
    max_peak_dbfs: float = -1.0
    # Ideal window from the spec.
    ideal_min_peak_dbfs: float = -6.0
    ideal_max_peak_dbfs: float = -3.0

    max_clipping_ratio: float = 0.0005  # 0.05 %
    max_noise_floor_dbfs: float = -50.0

    min_lead_silence_ms: float = 150.0
    max_lead_silence_ms: float = 1500.0
    min_trail_silence_ms: float = 150.0
    max_trail_silence_ms: float = 1500.0

    @classmethod
    def for_profile(cls, profile: str) -> "QCThresholds":
        """TTS needs a cleaner signal than ASR; anything else gets the safe default."""
        if profile.lower() == "tts":
            return cls(min_snr_db=40.0)
        return cls()


ASR_THRESHOLDS = QCThresholds.for_profile("asr")
TTS_THRESHOLDS = QCThresholds.for_profile("tts")
