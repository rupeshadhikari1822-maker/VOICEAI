"""Verdict and contributor-facing messages.

Every message names the physical thing to change -- move the mic, close the
window, turn the fan off -- not what the code measured. A contributor on a phone
in Dhading cannot act on "SNR 22 dB"; they can act on "पंखा/झ्याल बन्द गर्नुहोस्".
The measured value is still appended in parentheses so the operator debugging a
run can see it.
"""

from __future__ import annotations

from app.services.audio_qc.metrics import QCResult
from app.services.audio_qc.thresholds import QCThresholds


def apply_gate(r: QCResult, th: QCThresholds) -> None:
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
        r.warnings.append(
            f"अवधि {r.duration_s:.1f}s — आदर्श "
            f"{th.ideal_min_duration_s:.0f}–{th.ideal_max_duration_s:.0f}s।"
        )

    if r.clipping_ratio > th.max_clipping_ratio:
        r.codes.append("clipping")
        r.reasons.append(
            f"आवाज बिग्रिएको छ (clipping {r.clipping_ratio * 100:.2f}%) — "
            f"माइक अलि टाढा सार्नुहोस् वा बिस्तारै बोल्नुहोस्। (clipping)"
        )

    if r.peak_dbfs > th.max_peak_dbfs:
        r.codes.append("too_loud")
        r.reasons.append(
            f"आवाज धेरै ठूलो छ ({r.peak_dbfs:.1f} dBFS) — "
            f"माइक मुखबाट १५–२० सेमी टाढा राख्नुहोस्। (too loud)"
        )
    elif r.peak_dbfs < th.min_peak_dbfs:
        r.codes.append("too_quiet")
        r.reasons.append(
            f"आवाज धेरै सानो छ ({r.peak_dbfs:.1f} dBFS) — माइक नजिक ल्याउनुहोस् र "
            f"अलि ठूलो स्वरमा बोल्नुहोस्। (too quiet)"
        )
    elif not (th.ideal_min_peak_dbfs <= r.peak_dbfs <= th.ideal_max_peak_dbfs):
        r.warnings.append(
            f"स्तर {r.peak_dbfs:.1f} dBFS — आदर्श "
            f"{th.ideal_min_peak_dbfs:.0f} देखि {th.ideal_max_peak_dbfs:.0f} dBFS।"
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
            f"पछाडिको आवाज धेरै छ — पंखा/झ्याल बन्द गर्नुहोस् र शान्त कोठामा "
            f"फेरि रेकर्ड गर्नुहोस्। "
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
            f"सुरुको चुप्पी छोटो छ ({r.lead_silence_ms:.0f} ms) — "
            f"बोल्नु अघि आधा सेकेन्ड पर्खनुहोस्।"
        )

    if r.trail_silence_ms > th.max_trail_silence_ms:
        r.codes.append("trail_silence_long")
        r.reasons.append(
            f"अन्त्यमा धेरै लामो चुप्पी छ ({r.trail_silence_ms:.0f} ms) — "
            f"वाक्य सकिएको आधा सेकेन्डमा रोक्नुहोस्। (long trailing silence)"
        )
    elif r.trail_silence_ms < th.min_trail_silence_ms:
        r.warnings.append(
            f"अन्त्यको चुप्पी छोटो छ ({r.trail_silence_ms:.0f} ms) — "
            f"रोक्नु अघि आधा सेकेन्ड पर्खनुहोस्।"
        )
