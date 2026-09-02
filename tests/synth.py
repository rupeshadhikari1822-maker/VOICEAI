"""Synthetic audio for tests.

Real recordings can't be committed (they're personal data, and they're large),
so the QC tests are driven by generated signals with known properties. The
generator has to be voice-like enough that the frame-energy analysis behaves as
it would on speech: a flat sine wave has no syllable structure, so the speech
span detection would never be exercised.
"""

from __future__ import annotations

import io
import wave

import numpy as np

SR = 48000


def synth_speech(
    duration_s: float = 3.0, sr: int = SR, rms_dbfs: float = -16.0
) -> np.ndarray:
    """Voice-like: harmonic stack, moving pitch, syllable envelope."""
    t = np.arange(int(sr * duration_s)) / sr
    f0 = 120.0 + 18.0 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    sig = sum((1.0 / k) * np.sin(k * phase) for k in range(1, 12))
    # Syllable rate ~3.5 Hz, roughly conversational.
    envelope = (0.5 * (1 + np.sin(2 * np.pi * 3.5 * t - np.pi / 2))) ** 1.5
    sig = sig * (0.15 + 0.85 * envelope)
    sig = sig / max(float(np.sqrt(np.mean(sig**2))), 1e-12)
    return (sig * (10 ** (rms_dbfs / 20.0))).astype(np.float32)


def with_room(
    speech: np.ndarray, noise_dbfs: float, pad_s: float = 0.3, sr: int = SR
) -> np.ndarray:
    """Pad with room tone at both ends and mix noise across the whole take."""
    pad = int(sr * pad_s)
    body = np.concatenate(
        [np.zeros(pad, np.float32), speech, np.zeros(pad, np.float32)]
    )
    rng = np.random.default_rng(20260901)
    noise = rng.standard_normal(body.size).astype(np.float32)
    noise *= (10 ** (noise_dbfs / 20.0)) / max(
        float(np.sqrt(np.mean(noise**2))), 1e-12
    )
    return body + noise


def to_wav(samples: np.ndarray, sr: int = SR) -> bytes:
    pcm = np.clip(samples, -1.0, 1.0)
    ints = np.where(pcm < 0, pcm * 32768.0, pcm * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(ints.tobytes())
    return buf.getvalue()


def clean_take(**kwargs) -> bytes:
    """A take that should pass every gate. ~47 dB SNR."""
    return to_wav(with_room(synth_speech(**kwargs), noise_dbfs=-63.0))


def noisy_take(**kwargs) -> bytes:
    """A take that should fail on SNR. ~10 dB."""
    return to_wav(with_room(synth_speech(**kwargs), noise_dbfs=-26.0))
