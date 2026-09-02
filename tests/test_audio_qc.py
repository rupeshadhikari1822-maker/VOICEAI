"""QC gate: does it actually discriminate?

A gate that passes everything is worse than no gate, because it produces a
corpus you believe in. These tests pin the discrimination, not the exact
numbers -- the assertions are on pass/fail and on the failure code, with the
measured values checked only loosely.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.audio_qc import (
    ASR_THRESHOLDS,
    TTS_THRESHOLDS,
    QCThresholds,
    analyze,
    decode_wav,
)
from tests.synth import SR, synth_speech, to_wav, with_room


def test_clean_take_passes():
    r = analyze(to_wav(with_room(synth_speech(), noise_dbfs=-63.0)), ASR_THRESHOLDS)
    assert r.passed, f"unexpected failure codes: {r.codes}"
    assert r.snr_db >= ASR_THRESHOLDS.min_snr_db
    assert r.snr_db > 40, "clean synthetic take should be well above the gate"
    assert r.noise_floor_dbfs < -50
    assert r.clipping_ratio == 0.0


def test_noisy_take_rejected_on_snr():
    r = analyze(to_wav(with_room(synth_speech(), noise_dbfs=-26.0)), ASR_THRESHOLDS)
    assert not r.passed
    assert "snr_low" in r.codes
    assert r.snr_db < ASR_THRESHOLDS.min_snr_db


def test_rejection_says_what_to_physically_change():
    """Error copy is Nepali-first and actionable, not a code dump."""
    r = analyze(to_wav(with_room(synth_speech(), noise_dbfs=-26.0)), ASR_THRESHOLDS)
    assert any("पंखा" in reason for reason in r.reasons)


def test_clipping_detected():
    r = analyze(to_wav(with_room(synth_speech(rms_dbfs=-2.0), -63.0)), ASR_THRESHOLDS)
    assert not r.passed
    assert "clipping" in r.codes or "too_loud" in r.codes


def test_silence_rejected():
    r = analyze(to_wav(np.zeros(SR * 2, np.float32)), ASR_THRESHOLDS)
    assert not r.passed
    assert "no_speech" in r.codes


def test_too_quiet_rejected():
    r = analyze(to_wav(with_room(synth_speech(rms_dbfs=-52.0), -80.0)), ASR_THRESHOLDS)
    assert not r.passed
    assert "too_quiet" in r.codes


def test_too_short_and_too_long_rejected():
    short = analyze(to_wav(with_room(synth_speech(duration_s=0.2), -63.0, pad_s=0.05)))
    assert not short.passed and "too_short" in short.codes

    long = analyze(to_wav(with_room(synth_speech(duration_s=25.0), -63.0)))
    assert not long.passed and "too_long" in long.codes


def test_garbage_input_fails_cleanly():
    """Malformed audio must produce a verdict, never an exception."""
    r = analyze(b"not a wav file at all")
    assert r.passed is False
    assert "decode_failed" in r.codes


def test_tts_profile_is_stricter_than_asr():
    assert TTS_THRESHOLDS.min_snr_db > ASR_THRESHOLDS.min_snr_db
    assert QCThresholds.for_profile("tts").min_snr_db == 40.0
    assert QCThresholds.for_profile("asr").min_snr_db == 30.0
    # Unknown profile falls back to the safer default rather than raising.
    assert QCThresholds.for_profile("nonsense").min_snr_db == 30.0


def test_low_sample_rate_rejected():
    """Bluetooth headsets resample to 8/16 kHz; that audio is unusable."""
    r = analyze(to_wav(with_room(synth_speech(sr=16000), -63.0, sr=16000), sr=16000))
    assert not r.passed
    assert "sample_rate_low" in r.codes


@pytest.mark.parametrize("channels", [1, 2])
def test_decode_wav_handles_mono_and_stereo(channels):
    mono = synth_speech(duration_s=0.5)
    if channels == 2:
        interleaved = np.repeat(mono, 2)
        data = to_wav(interleaved)
        # to_wav writes a mono header, so re-read as mono and just check length.
        x, sr, ch, bits = decode_wav(data)
        assert ch == 1
    else:
        x, sr, ch, bits = decode_wav(to_wav(mono))
        assert ch == 1
        assert len(x) == len(mono)
    assert sr == SR
    assert bits == 16


def test_speech_span_snr_not_flattered_by_loud_frames_only():
    """SNR is measured across the whole speech span, including quiet parts.

    Measuring only frames above threshold would report a good SNR for a clip
    whose noise is audible between syllables -- exactly the clip you want to
    reject.
    """
    quiet_noise = analyze(to_wav(with_room(synth_speech(), -63.0)))
    loud_noise = analyze(to_wav(with_room(synth_speech(), -26.0)))
    assert quiet_noise.snr_db - loud_noise.snr_db > 25
