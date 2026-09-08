"""Resampling and loudness normalisation for exported audio.

The 48 kHz masters in raw/ are never touched -- every function here reads
decoded samples and returns new ones. Mirrors the DSP scripts/export_dataset.py
used to do inline, unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# ITU-R BS.1770 target used by most TTS recipes.
TTS_TARGET_LUFS = -23.0


def resample(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Polyphase resample. Falls back to linear if scipy is absent."""
    if src_sr == dst_sr:
        return x
    try:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(src_sr, dst_sr)
        return resample_poly(x, dst_sr // g, src_sr // g).astype(np.float32)
    except ImportError:
        print(
            "  warning: scipy not installed, falling back to linear interpolation.\n"
            "           Install scipy for a proper anti-aliased resample.",
            file=sys.stderr,
        )
        n_out = int(round(len(x) * dst_sr / src_sr))
        return np.interp(
            np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x
        ).astype(np.float32)


def normalize_loudness(x: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    """Loudness-normalise for TTS. Uses pyloudnorm when available."""
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(x.astype(np.float64))
        if not np.isfinite(loudness):
            return x
        gain = 10 ** ((target_lufs - loudness) / 20.0)
    except ImportError:
        # RMS stand-in. Not BS.1770, but consistent across the set, which is
        # what matters for a single-voice TTS corpus.
        rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
        if rms <= 0:
            return x
        gain = 10 ** ((target_lufs + 3.0) / 20.0) / rms

    y = x * gain
    # Normalising can push peaks past full scale; back off rather than clip.
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.99:
        y = y * (0.99 / peak)
    return y.astype(np.float32)


def write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(x, -1.0, 1.0)
    ints = np.where(pcm < 0, pcm * 32768.0, pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(ints.tobytes())
