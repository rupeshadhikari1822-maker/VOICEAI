#!/usr/bin/env python
"""Honour a withdrawal request.

    python scripts/withdraw.py 01JQ...  --dry-run
    python scripts/withdraw.py 01JQ...  --confirm

Consent that cannot be revoked is not consent. This does three things, in an
order chosen so a crash never leaves data exposed:

  1. deletes the audio objects from storage
  2. tombstones the clip rows, so no export can pick them up
  3. erases the PII columns and stamps `withdrawn_at`

Clip rows are kept as tombstones rather than deleted, so that a dataset already
exported can be diffed against the current corpus to see what must be pulled.
The tombstone carries no personal data and no audio.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Clip, ConsentRecord, Speaker  # noqa: E402
from app.storage import get_storage  # noqa: E402


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("speaker_id")
    parser.add_argument("--confirm", action="store_true", help="actually do it")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen")
    args = parser.parse_args()

    if not args.confirm and not args.dry_run:
        print("refusing to run without --confirm (or --dry-run)", file=sys.stderr)
        return 2

    storage = get_storage()

    with SessionLocal() as db:
        speaker = db.get(Speaker, args.speaker_id)
        if speaker is None:
            print(f"no such speaker: {args.speaker_id}", file=sys.stderr)
            return 1

        if speaker.withdrawn_at is not None:
            print(f"speaker {speaker.id} already withdrawn at {speaker.withdrawn_at}")
            return 0

        clips = db.query(Clip).filter(Clip.speaker_id == speaker.id).all()
        consents = (
            db.query(ConsentRecord)
            .filter(ConsentRecord.speaker_id == speaker.id)
            .all()
        )
        spoken = [c.spoken_clip_key for c in consents if c.spoken_clip_key]

        print(f"speaker    : {speaker.id}")
        print(f"clips      : {len(clips)}")
        print(f"consent    : {len(consents)} record(s), {len(spoken)} spoken clip(s)")
        print(f"PII fields : name={bool(speaker.name)} email={bool(speaker.email)} "
              f"phone={bool(speaker.phone)} caste={bool(speaker.caste_ethnicity)}")

        if args.dry_run:
            print("\ndry run -- nothing changed")
            return 0

        # 1. objects first: if this fails, the DB still points at them.
        deleted = 0
        for clip in clips:
            try:
                storage.delete(clip.object_key)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  could not delete {clip.object_key}: {exc}", file=sys.stderr)
        for key in spoken:
            try:
                storage.delete(key)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  could not delete {key}: {exc}", file=sys.stderr)

        # Sweep anything the per-clip deletes missed: orphaned raw objects from
        # an interrupted upload, and derived copies written by an export.
        # Keys are raw/{lang}/{speaker}/... and derived/{rate}/{lang}/{speaker}/...,
        # so the speaker id is never the first path segment.
        langs = {clip.lang for clip in clips} or {"ne"}
        prefixes = [f"consent/{speaker.id}/"]
        for lang in langs:
            prefixes.append(f"raw/{lang}/{speaker.id}/")
            for rate in ("16k", "22k"):
                prefixes.append(f"derived/{rate}/{lang}/{speaker.id}/")

        for prefix in prefixes:
            try:
                deleted += storage.delete_prefix(prefix)
            except Exception as exc:  # noqa: BLE001
                print(f"  could not sweep {prefix}: {exc}", file=sys.stderr)

        # 2. tombstone the clips.
        for clip in clips:
            clip.tombstoned = True
            clip.client_metrics = None

        # 3. erase PII last.
        speaker.name = None
        speaker.email = None
        speaker.phone = None
        speaker.caste_ethnicity = None
        speaker.municipality = None
        speaker.ward = None
        speaker.withdrawn_at = datetime.now(timezone.utc)

        db.commit()

    print(f"\nwithdrawn. objects deleted: {deleted}, clips tombstoned: {len(clips)}")
    print("re-run scripts/export_dataset.py to regenerate exports without this speaker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
