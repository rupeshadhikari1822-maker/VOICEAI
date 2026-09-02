#!/usr/bin/env python
"""Find prompts that are the problem, not the speakers.

    python scripts/prompt_health.py
    python scripts/prompt_health.py --deactivate

This is what structured reject reasons are for. One person misreading a sentence
is a reader having a bad moment. Five different people misreading the *same*
sentence is an ambiguous sentence, and no amount of re-recording will fix it.
Numerals and long conjuncts are the usual culprits -- "दुई हजार पचहत्तर" can be
read several defensible ways.

`--deactivate` sets `Prompt.active = false` above the rejection threshold, but
only with enough **distinct speakers** to support the conclusion. A prompt read
badly five times by one person is not evidence about the prompt.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models import Clip, Prompt  # noqa: E402


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="ne")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="rejection rate above which a prompt is suspect (default 0.4)",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=5,
        help="distinct speakers required before judging a prompt (default 5)",
    )
    parser.add_argument(
        "--deactivate",
        action="store_true",
        help="set active=false on prompts over the threshold",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        clips = (
            db.query(Clip)
            .filter(
                Clip.lang == args.lang,
                Clip.verify_status.in_(("verified", "rejected")),
                Clip.tombstoned.is_(False),
            )
            .all()
        )

        if not clips:
            print("no reviewed clips yet -- run the review pass first")
            return 0

        reviewed: Counter[str] = Counter()
        rejected: Counter[str] = Counter()
        speakers: dict[str, set[str]] = {}
        reasons: dict[str, Counter[str]] = {}

        for clip in clips:
            reviewed[clip.prompt_id] += 1
            speakers.setdefault(clip.prompt_id, set()).add(clip.speaker_id)
            if clip.verify_status == "rejected":
                rejected[clip.prompt_id] += 1
                reasons.setdefault(clip.prompt_id, Counter())[
                    clip.reject_reason or "unspecified"
                ] += 1

        rows = []
        for prompt_id, n in reviewed.items():
            bad = rejected.get(prompt_id, 0)
            rate = bad / n
            distinct = len(speakers[prompt_id])
            rows.append((rate, prompt_id, n, bad, distinct))
        rows.sort(reverse=True)

        print("=" * 72)
        print(f"  prompt health  ({args.lang})")
        print("=" * 72)
        print(f"  prompts with reviewed clips : {len(rows)}")
        print(f"  threshold                   : {args.threshold:.0%} rejection")
        print(f"  minimum distinct speakers   : {args.min_speakers}")

        suspect = [
            r for r in rows if r[0] > args.threshold and r[4] >= args.min_speakers
        ]
        watch = [
            r
            for r in rows
            if r[0] > args.threshold and r[4] < args.min_speakers
        ]

        if suspect:
            print(f"\n  SUSPECT ({len(suspect)}) -- enough speakers to blame the prompt")
            for rate, pid, n, bad, distinct in suspect:
                prompt = db.get(Prompt, pid)
                top = reasons.get(pid, Counter()).most_common(2)
                why = ", ".join(f"{r}×{c}" for r, c in top)
                print(f"\n    {pid}  {rate:.0%} rejected ({bad}/{n}, {distinct} speakers)")
                print(f"      {prompt.text if prompt else '(deleted)'}")
                print(f"      reasons: {why}")

        if watch:
            print(f"\n  NOT ENOUGH DATA ({len(watch)}) -- high rejection, too few speakers")
            for rate, pid, n, bad, distinct in watch:
                print(f"    {pid}  {rate:.0%} ({bad}/{n}) from only {distinct} speaker(s)")

        if not suspect and not watch:
            print("\n  no prompt is over the threshold. Nothing to do.")

        if args.deactivate and suspect:
            for _rate, pid, _n, _bad, _d in suspect:
                prompt = db.get(Prompt, pid)
                if prompt is not None:
                    prompt.active = False
            db.commit()
            print(f"\n  deactivated {len(suspect)} prompt(s). They will not be served again.")
        elif suspect:
            print("\n  re-run with --deactivate to take these out of rotation.")

        print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
