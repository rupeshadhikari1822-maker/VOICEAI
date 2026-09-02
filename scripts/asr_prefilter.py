#!/usr/bin/env python
"""Shrink the human review queue with ASR.

    python scripts/asr_prefilter.py --dry-run
    python scripts/asr_prefilter.py --limit 200
    python scripts/asr_prefilter.py --model medium --lang ne

Because the target text is already known, this is a far easier problem than open
transcription: we only need to know whether the reader said roughly the printed
sentence. Clips well below the CER threshold are auto-verified, clips well above
it are auto-rejected as misreads, and only the ambiguous middle reaches a human.
That typically removes 60-80% of the queue.

Batch and resumable on purpose. Transcription is slow and must never happen
inside a request; a clip that already has `asr_model` set is skipped, so an
interrupted run can simply be re-run.

Requires the optional ASR extra:

    pip install faster-whisper

Without it this script exits with a message and **the review UI still works
fully** -- the human path never depends on the optional path.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.ids import new_ulid  # noqa: E402
from app.models import Clip, ReviewEvent, Speaker  # noqa: E402
from app.services.review.asr_prefilter import decide  # noqa: E402
from app.services.storage import StorageError, get_storage  # noqa: E402


def load_model(name: str):
    """Load faster-whisper, or explain clearly why we cannot."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "faster-whisper is not installed, so the ASR pre-filter cannot run.\n"
            "\n"
            "    pip install faster-whisper\n"
            "\n"
            "This is optional. Without it every clip that passed QC simply goes\n"
            "to a human reviewer, and /review works exactly as it does now.",
            file=sys.stderr,
        )
        return None

    print(f"loading model '{name}' (first run downloads weights)...")
    # int8 on CPU is the practical default: a GPU is not assumed, and the
    # accuracy cost is irrelevant when the output is only compared to a known
    # target rather than read by a person.
    return WhisperModel(name, device="auto", compute_type="int8")


def transcribe(model, wav_bytes: bytes, lang: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        fh.write(wav_bytes)
        path = fh.name
    try:
        segments, _info = model.transcribe(path, language=lang, beam_size=5)
        return " ".join(seg.text for seg in segments).strip()
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    use_utf8()
    settings = get_settings()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="ne")
    parser.add_argument("--model", default=settings.asr_model)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--dry-run", action="store_true", help="report decisions, change nothing"
    )
    parser.add_argument(
        "--redo", action="store_true", help="re-transcribe clips that already have ASR"
    )
    args = parser.parse_args()

    storage = get_storage()

    with SessionLocal() as db:
        query = (
            db.query(Clip)
            .join(Speaker, Clip.speaker_id == Speaker.id)
            .filter(
                Clip.lang == args.lang,
                Clip.qc_status == "passed",
                Clip.tombstoned.is_(False),
                Speaker.withdrawn_at.is_(None),
            )
        )
        if not args.redo:
            # Resumability: skip anything a previous run already handled.
            query = query.filter(Clip.asr_model.is_(None))

        clips = query.order_by(Clip.created_at).all()
        if args.limit:
            clips = clips[: args.limit]

        if not clips:
            print("nothing to do: no clips need transcription")
            return 0

        print(
            f"{len(clips)} clip(s) to transcribe  "
            f"(auto-verify CER < {settings.asr_auto_verify_cer}, "
            f"auto-reject CER > {settings.asr_auto_reject_cer})"
        )

        model = load_model(args.model)
        if model is None:
            return 2

        counts = {"verified": 0, "rejected": 0, "unverified": 0, "skipped": 0}

        for n, clip in enumerate(clips, 1):
            try:
                wav = storage.get_bytes(clip.object_key)
            except StorageError as exc:
                print(f"  [{n}/{len(clips)}] {clip.id}: {exc}", file=sys.stderr)
                counts["skipped"] += 1
                continue

            text = transcribe(model, wav, args.lang)
            verdict = decide(clip.prompt_text, text, settings)
            counts[verdict.verify_status] += 1

            flag = "auto" if verdict.auto else "->human"
            print(
                f"  [{n}/{len(clips)}] {clip.id} CER={verdict.cer:.3f} "
                f"{verdict.verify_status:<10} {flag}"
            )

            if args.dry_run:
                continue

            # Written even when auto-verifying: someone auditing the auto-pass
            # decisions needs to see what the model actually heard.
            clip.asr_text = text
            clip.asr_cer = round(verdict.cer, 4)
            clip.asr_model = args.model
            clip.review_priority = verdict.review_priority

            if verdict.auto:
                clip.verify_status = verdict.verify_status
                clip.verified_by = f"asr:{args.model}"
                clip.verified_at = datetime.now(timezone.utc)
                clip.reject_reason = verdict.reject_reason
                # Prefixed reviewer keeps machine decisions out of agreement
                # statistics and makes them bulk-revertible.
                db.add(
                    ReviewEvent(
                        id=new_ulid(),
                        clip_id=clip.id,
                        reviewer=f"asr:{args.model}",
                        action=verdict.verify_status,
                        reason=verdict.reject_reason,
                        notes=f"CER={verdict.cer:.3f}",
                    )
                )

            if n % 25 == 0:
                db.commit()

        if not args.dry_run:
            db.commit()

    total = sum(counts.values())
    auto = counts["verified"] + counts["rejected"]
    print("\n" + "=" * 54)
    print(f"  auto-verified : {counts['verified']}")
    print(f"  auto-rejected : {counts['rejected']}")
    print(f"  left to human : {counts['unverified']}")
    if counts["skipped"]:
        print(f"  skipped       : {counts['skipped']}")
    if total:
        print(f"  queue reduced : {auto / total * 100:.0f}%")
    if args.dry_run:
        print("\n  dry run -- nothing was written")
    print("=" * 54)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
