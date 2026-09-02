"""Measurement: decode the WAV and derive the numbers. No policy here.

The SNR definition is the part worth understanding. We locate the speech span
(first to last frame above the noise floor + 10 dB), take the RMS across that
whole span -- not only the frames above threshold -- and subtract the floor.
Measuring only the loud frames would flatter a noisy recording, because it would
skip the quiet parts between syllables where the noise is most audible relative
to the voice. That is exactly the recording you want to reject.
"""

from __future__ import annotations

import io
import wave
from dataclasses import asdict, dataclass, field

import numpy as np

# int16 full scale. A sample at or beyond this is a clipped sample.
FULL_SCALE = 32767
EPS = 1e-12


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


def dbfs(x: float) -> float:
    return float(20.0 * np.log10(max(float(x), EPS)))


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


def frame_energies(
    x: np.ndarray, sample_rate: int, frame_ms: float = 20.0, hop_ms: float = 10.0
) -> tuple[np.ndarray, int]:
    """Short-time frame RMS in dBFS, plus the hop size in samples."""
    frame = max(1, int(sample_rate * frame_ms / 1000.0))
    hop = max(1, int(sample_rate * hop_ms / 1000.0))
    if x.size < frame:
        return np.array([dbfs(np.sqrt(np.mean(x**2)) if x.size else 0.0)]), hop

    n_frames = 1 + (x.size - frame) // hop
    # Strided view, so a long clip is not copied frame by frame.
    strides = (x.strides[0] * hop, x.strides[0])
    frames = np.lib.stride_tricks.as_strided(
        x, shape=(n_frames, frame), strides=strides
    )
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, EPS)), hop


def measure(data: bytes) -> QCResult:
    """Fill in every metric. Sets codes only for conditions that stop measurement."""
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
    result.peak_dbfs = round(dbfs(peak), 2)
    result.rms_dbfs = round(dbfs(np.sqrt(np.mean(x.astype(np.float64) ** 2))), 2)

    clipped = int(np.count_nonzero(np.abs(x) >= (FULL_SCALE - 0.5) / 32768.0))
    result.clipping_ratio = round(clipped / float(x.size), 6)

    # --- noise floor, speech span, SNR ---------------------------------
    frame_db, hop = frame_energies(x, sample_rate)
    noise_floor = float(np.percentile(frame_db, 10))
    result.noise_floor_dbfs = round(noise_floor, 2)

    voiced_idx = np.flatnonzero(frame_db > (noise_floor + 10.0))

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
    speech_rms_db = dbfs(np.sqrt(np.mean(span.astype(np.float64) ** 2)))

    result.snr_db = round(speech_rms_db - noise_floor, 2)
    result.lead_silence_ms = round(start / sample_rate * 1000.0, 1)
    result.trail_silence_ms = round((x.size - end) / sample_rate * 1000.0, 1)

    return result
