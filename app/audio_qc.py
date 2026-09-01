"""Server-side audio quality control.

This module is authoritative. The browser computes the same metrics for instant
feedback, but every clip is re-analysed here from the bytes that actually landed
in storage. If the two disagree, this one wins.

Metrics, all derived from the decoded PCM:

  peak_dbfs         highest absolute sample
  rms_dbfs          overall level
  noise_floor_dbfs  10th percentile of short-frame energy (the room tone)
  snr_db            speech-span RMS minus the noise floor
  clipping_ratio    fraction of samples sitting at digital full scale
  lead/trail silence  how much room tone pads the utterance

The SNR definition matters. We locate the speech span (first to last frame above
the noise floor + 10 dB), take the RMS across that whole span -- not only the
frames above threshold -- and subtract the floor. Measuring only the loud frames
would flatter a noisy recording, because it would skip the quiet parts where the
noise is most audible relative to the voice.
"""

from __future__ import annotations

import io
import wave
from dataclasses import asdict, dataclass, field

import numpy as np

# int16 full scale. A sample at or beyond this is a clipped sample.
_FULL_SCALE = 32767
_EPS = 1e-12


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
        if profile.lower() == "tts":
            return cls(min_snr_db=40.0)
        return cls()


ASR_THRESHOLDS = QCThresholds.for_profile("asr")
TTS_THRESHOLDS = QCThresholds.for_profile("tts")


@dataclass
class QCResult:
    passed: bool = False
    # Machine-readable failure codes, e.g. "snr_low".
    codes: list[str] = field(default_factory=list)
    # Nepali-first, action-oriented messages for the contributor.
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    duration_s: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bit_depth: int = 0
    peak_dbfs: float = 0.0
    rms_dbfs: float = 0.0
    noise_floor_dbfs: float = 0.0
    snr_db: float = 0.0
    clipping_ratio: float = 0.0
    lead_silence_ms: float = 0.0
    trail_silence_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _dbfs(x: float) -> float:
    return float(20.0 * np.log10(max(float(x), _EPS)))


def decode_wav(data: bytes) -> tuple[np.ndarray, int, int, int]:
    """Decode a RIFF/WAV blob to mono float32 in [-1, 1].

    Returns (samples, sample_rate, channels, bit_depth). Raises ValueError on
    anything that is not 8/16/32-bit integer PCM.
    """
    with wave.open(io.BytesIO(data), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if sampwidth == 2:
        ints = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        scale = 32768.0
    elif sampwidth == 4:
        ints = np.frombuffer(raw, dtype="<i4").astype(np.float32)
        scale = 2147483648.0
    elif sampwidth == 1:
        # 8-bit WAV is unsigned, centred on 128.
        ints = (np.frombuffer(raw, dtype="<u1").astype(np.float32) - 128.0) * 256.0
        scale = 32768.0
    else:
        raise ValueError(f"unsupported sample width: {sampwidth * 8}-bit")

    if channels > 1:
        usable = (ints.size // channels) * channels
        ints = ints[:usable].reshape(-1, channels).mean(axis=1)

    return ints / scale, sample_rate, channels, sampwidth * 8


def _frame_energies(
    x: np.ndarray, sample_rate: int, frame_ms: float = 20.0, hop_ms: float = 10.0
) -> tuple[np.ndarray, int]:
    """Short-time frame RMS in dBFS, plus the hop size in samples."""
    frame = max(1, int(sample_rate * frame_ms / 1000.0))
    hop = max(1, int(sample_rate * hop_ms / 1000.0))
    if x.size < frame:
        return np.array([_dbfs(np.sqrt(np.mean(x**2)) if x.size else 0.0)]), hop

    n_frames = 1 + (x.size - frame) // hop
    # Strided view, so a long clip does not get copied frame by frame.
    strides = (x.strides[0] * hop, x.strides[0])
    frames = np.lib.stride_tricks.as_strided(x, shape=(n_frames, frame), strides=strides)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, _EPS)), hop


def analyze(data: bytes, thresholds: QCThresholds | None = None) -> QCResult:
    """Measure a WAV blob and decide whether it is fit for the corpus."""
    th = thresholds or ASR_THRESHOLDS
    result = QCResult()

    try:
        x, sample_rate, channels, bit_depth = decode_wav(data)
    except Exception as exc:  # noqa: BLE001 - surfaced to the contributor
        result.codes.append("decode_failed")
        result.reasons.append(
            f"अडियो फाइल पढ्न सकिएन — फेरि रेकर्ड गर्नुहोस्। "
            f"(could not decode audio: {exc})"
        )
        return result

    result.sample_rate = sample_rate
    result.channels = channels
    result.bit_depth = bit_depth

    if x.size == 0:
        result.codes.append("empty")
        result.reasons.append("रेकर्डिङ खाली छ — फेरि प्रयास गर्नुहोस्। (empty recording)")
        return result

    result.duration_s = round(x.size / float(sample_rate), 3)

    # --- level metrics -------------------------------------------------
    peak = float(np.max(np.abs(x)))
    result.peak_dbfs = round(_dbfs(peak), 2)
    result.rms_dbfs = round(_dbfs(np.sqrt(np.mean(x.astype(np.float64) ** 2))), 2)

    clipped = int(np.count_nonzero(np.abs(x) >= (_FULL_SCALE - 0.5) / 32768.0))
    result.clipping_ratio = round(clipped / float(x.size), 6)

    # --- noise floor, speech span, SNR ---------------------------------
    frame_db, hop = _frame_energies(x, sample_rate)
    noise_floor = float(np.percentile(frame_db, 10))
    result.noise_floor_dbfs = round(noise_floor, 2)

    voiced = frame_db > (noise_floor + 10.0)
    voiced_idx = np.flatnonzero(voiced)

    if voiced_idx.size == 0:
        result.snr_db = 0.0
        result.lead_silence_ms = round(result.duration_s * 1000.0, 1)
        result.trail_silence_ms = 0.0
        result.codes.append("no_speech")
        result.reasons.append(
            "कुनै आवाज पत्ता लागेन — माइक नजिक ल्याएर फेरि बोल्नुहोस्। (no speech detected)"
        )
        return result

    first, last = int(voiced_idx[0]), int(voiced_idx[-1])
    start = first * hop
    end = min(x.size, last * hop + hop)
    span = x[start:end]
    speech_rms_db = _dbfs(np.sqrt(np.mean(span.astype(np.float64) ** 2)))

    result.snr_db = round(speech_rms_db - noise_floor, 2)
    result.lead_silence_ms = round(start / sample_rate * 1000.0, 1)
    result.trail_silence_ms = round((x.size - end) / sample_rate * 1000.0, 1)

    _apply_gate(result, th)
    result.passed = not result.codes
    return result


def _apply_gate(r: QCResult, th: QCThresholds) -> None:
    """Populate codes/reasons/warnings from the measured metrics."""

    if r.sample_rate < th.min_sample_rate:
        r.codes.append("sample_rate_low")
        r.reasons.append(
            f"रेकर्डिङ गुणस्तर कम छ ({r.sample_rate} Hz) — ब्लुटुथ हेडसेट नचलाउनुहोस्, "
            f"तार भएको माइक प्रयोग गर्नुहोस्। (sample rate below {th.min_sample_rate} Hz)"
        )
    elif r.sample_rate != th.target_sample_rate:
        r.warnings.append(
            f"{r.sample_rate} Hz मा रेकर्ड भयो, {th.target_sample_rate} Hz अपेक्षित।"
        )

    if r.channels != 1:
        r.warnings.append(f"{r.channels} च्यानल आयो, मोनो अपेक्षित। (expected mono)")

    if r.bit_depth != 16:
        r.warnings.append(f"{r.bit_depth}-bit आयो, 16-bit अपेक्षित।")

    if r.duration_s < th.min_duration_s:
        r.codes.append("too_short")
        r.reasons.append(
            f"रेकर्डिङ धेरै छोटो छ ({r.duration_s:.1f}s) — पूरा वाक्य पढ्नुहोस्। (too short)"
        )
    elif r.duration_s > th.max_duration_s:
        r.codes.append("too_long")
        r.reasons.append(
            f"रेकर्डिङ धेरै लामो छ ({r.duration_s:.1f}s) — वाक्य सकिनेबित्तिकै रोक्नुहोस्। (too long)"
        )
    elif not (th.ideal_min_duration_s <= r.duration_s <= th.ideal_max_duration_s):
        r.warnings.append(f"अवधि {r.duration_s:.1f}s — आदर्श {th.ideal_min_duration_s:.0f}–{th.ideal_max_duration_s:.0f}s।")

    if r.clipping_ratio > th.max_clipping_ratio:
        r.codes.append("clipping")
        r.reasons.append(
            f"आवाज बिग्रिएको छ (clipping {r.clipping_ratio * 100:.2f}%) — "
            f"माइक अलि टाढा सार्नुहोस् वा बिस्तारै बोल्नुहोस्। (clipping)"
        )

    if r.peak_dbfs > th.max_peak_dbfs:
        r.codes.append("too_loud")
        r.reasons.append(
            f"आवाज धेरै ठूलो छ ({r.peak_dbfs:.1f} dBFS) — माइक मुखबाट १५–२० सेमी टाढा राख्नुहोस्। (too loud)"
        )
    elif r.peak_dbfs < th.min_peak_dbfs:
        r.codes.append("too_quiet")
        r.reasons.append(
            f"आवाज धेरै सानो छ ({r.peak_dbfs:.1f} dBFS) — माइक नजिक ल्याउनुहोस् र अलि ठूलो स्वरमा बोल्नुहोस्। (too quiet)"
        )
    elif not (th.ideal_min_peak_dbfs <= r.peak_dbfs <= th.ideal_max_peak_dbfs):
        r.warnings.append(
            f"स्तर {r.peak_dbfs:.1f} dBFS — आदर्श {th.ideal_min_peak_dbfs:.0f} देखि {th.ideal_max_peak_dbfs:.0f} dBFS।"
        )

    if r.noise_floor_dbfs > th.max_noise_floor_dbfs:
        r.codes.append("noise_floor_high")
        r.reasons.append(
            f"पछाडिको आवाज धेरै छ ({r.noise_floor_dbfs:.0f} dBFS) — "
            f"पंखा/झ्याल बन्द गर्नुहोस्। (background noise too high)"
        )

    if r.snr_db < th.min_snr_db:
        r.codes.append("snr_low")
        r.reasons.append(
            f"पछाडिको आवाज धेरै छ — पंखा/झ्याल बन्द गर्नुहोस् र शान्त कोठामा फेरि रेकर्ड गर्नुहोस्। "
            f"(SNR {r.snr_db:.0f} dB, needs {th.min_snr_db:.0f} dB)"
        )

    if r.lead_silence_ms > th.max_lead_silence_ms:
        r.codes.append("lead_silence_long")
        r.reasons.append(
            f"सुरुमा धेरै लामो चुप्पी छ ({r.lead_silence_ms:.0f} ms) — "
            f"रेकर्ड थालेको आधा सेकेन्डमै बोल्न सुरु गर्नुहोस्। (long leading silence)"
        )
    elif r.lead_silence_ms < th.min_lead_silence_ms:
        r.warnings.append(
            f"सुरुको चुप्पी छोटो छ ({r.lead_silence_ms:.0f} ms) — बोल्नु अघि आधा सेकेन्ड पर्खनुहोस्।"
        )

    if r.trail_silence_ms > th.max_trail_silence_ms:
        r.codes.append("trail_silence_long")
        r.reasons.append(
            f"अन्त्यमा धेरै लामो चुप्पी छ ({r.trail_silence_ms:.0f} ms) — "
            f"वाक्य सकिएको आधा सेकेन्डमा रोक्नुहोस्। (long trailing silence)"
        )
    elif r.trail_silence_ms < th.min_trail_silence_ms:
        r.warnings.append(
            f"अन्त्यको चुप्पी छोटो छ ({r.trail_silence_ms:.0f} ms) — रोक्नु अघि आधा सेकेन्ड पर्खनुहोस्।"
        )
