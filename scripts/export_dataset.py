#!/usr/bin/env python
"""Turn the corpus into a training-ready dataset.

    python scripts/export_dataset.py --format asr --sr 16000 --out export_out/asr
    python scripts/export_dataset.py --format tts --sr 22050 --out export_out/tts
    python scripts/export_dataset.py --format ljspeech --out export_out/lj

Two invariants this script exists to protect:

1. **Splits are speaker-disjoint.** One voice never appears in both train and
   test. If it did, your test WER measures memorisation of a speaker rather than
   generalisation, and the number would be quietly, badly wrong.

2. **No PII leaves.** Rows are built from `Speaker.export_row()`, which returns
   a fixed set of non-identifying fields. Name, email, phone and caste are not
   reachable from here -- there is no flag that turns them on.

The 48 kHz masters in raw/ are never modified. Everything here is derived and
can be regenerated.

The pipeline itself lives in `app/services/export/` -- this script is just the
CLI argument handling and console reporting around it. The admin dashboard's
"Export dataset" download button (`GET /api/admin/export`) calls the same
pipeline, so both paths produce identical corpus semantics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.services.export import FORMAT_DEFAULTS, ExportEmpty, assign_splits, run_export  # noqa: E402,F401
from app.services.storage import get_storage  # noqa: E402

# `assign_splits` is re-exported (not used directly below) because
# tests/test_smoke.py imports it from this module -- keep that path working.


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", required=True, choices=sorted(FORMAT_DEFAULTS))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sr", type=int, help="target sample rate (per-format default)")
    parser.add_argument("--lang", default="ne")
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="only clips a human approved in the review pass",
    )
    parser.add_argument("--min-snr", type=float, default=None)
    parser.add_argument("--split-seed", default="voice-cloudfrm-v1")
    parser.add_argument("--train", type=float, default=0.90)
    parser.add_argument("--dev", type=float, default=0.05)
    parser.add_argument("--test", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    storage = get_storage()
    with SessionLocal() as db:
        try:
            result = run_export(
                db,
                storage,
                args.out,
                fmt=args.format,
                sr=args.sr,
                lang=args.lang,
                verified_only=args.verified_only,
                min_snr=args.min_snr,
                split_seed=args.split_seed,
                train=args.train,
                dev=args.dev,
                test=args.test,
                limit=args.limit,
            )
        except ExportEmpty:
            print("nothing to export: no clips matched the filters", file=sys.stderr)
            return 1

    print(f"\n  clips written : {len(result.manifest)}")
    for split in ("train", "dev", "test"):
        print(f"  {split:<13} : {result.per_split.get(split, 0)}")
    print(f"  audio         : {result.total_seconds / 3600:.2f} h")

    # Splits hold whole speakers, so with a handful of voices the requested
    # ratios simply cannot be met. Say so rather than shipping an empty split.
    empty = [s for s in ("train", "dev", "test") if not result.per_split.get(s)]
    if empty:
        print(
            f"\n  note: {', '.join(empty)} split(s) are empty. Splits are"
            f" speaker-disjoint, and {result.n_speakers} speaker(s) cannot be"
            f" divided into the requested ratios. Recruit more speakers, or"
            f" pass --train/--dev/--test to rebalance."
        )
    if result.failures:
        print(f"  skipped       : {result.failures} (see stderr)")
    if result.speaker_overlap:
        print(
            f"\nERROR: speaker overlap between splits: {sorted(result.speaker_overlap)}",
            file=sys.stderr,
        )
    print(f"\nwrote {result.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
