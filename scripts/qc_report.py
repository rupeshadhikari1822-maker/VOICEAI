#!/usr/bin/env python
"""Corpus health report.

    python scripts/qc_report.py
    python scripts/qc_report.py --lang ne --failures

Answers the questions you actually need before a training run: how many usable
hours do I have, how are they spread across speakers, and what is failing.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Clip, Prompt, Speaker  # noqa: E402


def _bar(n: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return ""
    filled = int(round(width * n / total))
    return "#" * filled + "." * (width - filled)


def _percentiles(values: list[float], points=(5, 25, 50, 75, 95)) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    out = []
    for p in points:
        idx = min(len(ordered) - 1, int(len(ordered) * p / 100))
        out.append(f"p{p}={ordered[idx]:.1f}")
    return "  ".join(out)


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="ne")
    parser.add_argument("--failures", action="store_true", help="list failing clips")
    args = parser.parse_args()

    with SessionLocal() as db:
        clips = (
            db.query(Clip)
            .filter(Clip.lang == args.lang, Clip.tombstoned.is_(False))
            .all()
        )
        speakers = db.query(Speaker).filter(Speaker.withdrawn_at.is_(None)).all()
        active_prompts = (
            db.query(Prompt)
            .filter(Prompt.lang == args.lang, Prompt.active.is_(True))
            .count()
        )

        if not clips:
            print(f"no clips recorded for lang={args.lang}")
            print(f"active prompts: {active_prompts}")
            return 0

        status = Counter(c.qc_status for c in clips)
        passed = [c for c in clips if c.qc_status == "passed"]
        failed = [c for c in clips if c.qc_status == "failed"]

        seconds = sum(c.duration_s or 0.0 for c in passed)
        by_speaker: dict[str, float] = defaultdict(float)
        for c in passed:
            by_speaker[c.speaker_id] += c.duration_s or 0.0

        print("=" * 62)
        print(f"  corpus report  ({args.lang})")
        print("=" * 62)
        print(f"  clips recorded     : {len(clips)}")
        for name in ("passed", "failed", "pending"):
            n = status.get(name, 0)
            print(f"    {name:<16} : {n:>6}  {_bar(n, len(clips))}")
        print(f"  usable audio       : {seconds / 3600:.2f} h  ({seconds / 60:.0f} min)")
        print(f"  speakers (usable)  : {len(by_speaker)} of {len(speakers)} registered")
        print(f"  active prompts     : {active_prompts}")
        if passed:
            print(f"  pass rate          : {len(passed) / len(clips) * 100:.1f}%")

        if passed:
            print("\n  quality of passing clips")
            print(f"    SNR dB       {_percentiles([c.snr_db for c in passed if c.snr_db is not None])}")
            print(f"    peak dBFS    {_percentiles([c.peak_dbfs for c in passed if c.peak_dbfs is not None])}")
            print(f"    noise dBFS   {_percentiles([c.noise_floor_dbfs for c in passed if c.noise_floor_dbfs is not None])}")
            print(f"    duration s   {_percentiles([c.duration_s for c in passed if c.duration_s is not None])}")

        if failed:
            print("\n  why clips fail")
            codes = Counter(code for c in failed for code in (c.qc_codes or []))
            for code, n in codes.most_common():
                print(f"    {code:<20} {n:>5}  {_bar(n, len(failed))}")

        if by_speaker:
            print("\n  top contributors")
            top = sorted(by_speaker.items(), key=lambda kv: -kv[1])[:10]
            for speaker_id, secs in top:
                print(f"    {speaker_id}  {secs / 60:>7.1f} min")

            # A corpus dominated by one voice trains a model that knows one
            # voice. Worth seeing before you commit to a training run.
            share = max(by_speaker.values()) / seconds if seconds else 0
            if share > 0.5 and len(by_speaker) > 1:
                print(
                    f"\n  note: one speaker is {share * 100:.0f}% of the audio."
                    " Recruit more voices before an ASR run."
                )

        if args.failures and failed:
            print("\n  failing clips")
            for c in failed[:50]:
                reasons = "; ".join(c.qc_reasons or [])[:100]
                print(f"    {c.id}  {','.join(c.qc_codes or [])}  {reasons}")

        print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
