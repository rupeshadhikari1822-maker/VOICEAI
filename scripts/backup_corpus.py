#!/usr/bin/env python
"""Back up the irreplaceable parts of the corpus, and audit what is there.

    python scripts/backup_corpus.py --verify
    python scripts/backup_corpus.py --dest /mnt/backup/voice
    python scripts/backup_corpus.py --dest /mnt/backup/voice --dry-run

R2 on its own is not a backup. It protects you against a disk failing; it does
not protect you against a script deleting the wrong prefix, a credential leak,
or an account problem. A bad `delete_prefix` removes audio exactly as
thoroughly as a dead drive, and re-recording is not an option -- the speakers
have gone home.

Two jobs:

**--verify** cross-checks the database against storage without downloading
anything. It answers two questions the database alone cannot: does every clip
row have a real object behind it, and is every object accounted for by a row.
Rows without objects are clips that will fail at export; objects without rows
are audio nobody can attribute to a consent record, which is a privacy problem
rather than a storage one.

**--dest** copies down what cannot be regenerated: the 48 kHz masters under
`raw/`, the spoken consent clips, and the database. Everything under `derived/`
is deliberately skipped -- `export_dataset.py` rebuilds it.

For bucket-to-bucket copies at scale, rclone is the better tool:

    rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw

This script exists for the parts rclone cannot do: the database dump, and the
consistency audit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models import Clip, ConsentRecord  # noqa: E402
from app.services.storage import StorageError, get_storage  # noqa: E402

# Everything under derived/ regenerates from raw/. Backing it up doubles the
# bill to store something a command can rebuild.
#
# This is an allow-list rather than a skip-list on purpose: both the copy and
# the audit enumerate only these prefixes, so a new prefix -- `_preflight/`
# probes, a scratch directory, anything a future feature adds -- is excluded by
# default rather than silently replicated to the archive forever.
BACKUP_PREFIXES = ("raw/", "consent/")

# Session probes written by GET /api/storage/preflight. Never backed up. Counted
# during the audit only so a missing bucket lifecycle rule becomes visible.
PREFLIGHT_PREFIX = "_preflight/"

# One probe per session. Past this, the lifecycle rule is probably missing.
PREFLIGHT_WARN_AT = 200


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} TB"


# --- audit --------------------------------------------------------------


def verify(storage) -> int:
    """Cross-check database rows against stored objects."""
    print("=" * 68)
    print("  corpus audit")
    print("=" * 68)

    stored: dict[str, int] = {}
    for prefix in BACKUP_PREFIXES:
        for key, size in storage.list_keys(prefix):
            stored[key] = size
    print(f"  objects in storage : {len(stored)}  ({human(sum(stored.values()))})")

    with SessionLocal() as db:
        clips = db.query(Clip).all()
        consents = [
            c for c in db.query(ConsentRecord).all() if c.spoken_clip_key
        ]

    live = [c for c in clips if not c.tombstoned]
    tombstoned = [c for c in clips if c.tombstoned]
    print(f"  clip rows          : {len(live)} live, {len(tombstoned)} tombstoned")
    print(f"  spoken consent     : {len(consents)}")

    problems = 0

    # A row with no object exports as a broken path, or silently drops.
    missing = [c for c in live if c.object_key not in stored]
    if missing:
        problems += len(missing)
        print(f"\n  MISSING OBJECTS ({len(missing)}) -- rows with no audio behind them")
        for clip in missing[:10]:
            print(f"    {clip.id}  {clip.object_key}")
        if len(missing) > 10:
            print(f"    ... and {len(missing) - 10} more")

    # An object still present for a tombstoned clip means a withdrawal did not
    # fully complete. That is a promise to a contributor left unkept.
    undeleted = [c for c in tombstoned if c.object_key in stored]
    if undeleted:
        problems += len(undeleted)
        print(f"\n  WITHDRAWN BUT STILL STORED ({len(undeleted)})")
        for clip in undeleted[:10]:
            print(f"    {clip.id}  {clip.object_key}")
        print("    Re-run scripts/withdraw.py for these speakers.")

    # Audio with no row cannot be tied to a consent record.
    known = {c.object_key for c in clips} | {c.spoken_clip_key for c in consents}
    orphans = sorted(set(stored) - known)
    if orphans:
        problems += len(orphans)
        print(f"\n  ORPHANED OBJECTS ({len(orphans)}) -- audio with no database row")
        for key in orphans[:10]:
            print(f"    {key}")
        if len(orphans) > 10:
            print(f"    ... and {len(orphans) - 10} more")
        print("    These cannot be tied to a consent record. Investigate before")
        print("    exporting; an interrupted upload is the usual innocent cause.")

    # Not corpus data, and never copied -- but if nothing is expiring them,
    # they accumulate one per session forever and nobody notices.
    probes = list(storage.list_keys(PREFLIGHT_PREFIX))
    if probes:
        probe_bytes = human(sum(size for _, size in probes))
        print(f"\n  preflight probes   : {len(probes)}  ({probe_bytes})")
        if len(probes) > PREFLIGHT_WARN_AT:
            print(
                f"    More than {PREFLIGHT_WARN_AT} probe objects under "
                f"{PREFLIGHT_PREFIX}. They are never backed up and carry no"
            )
            print("    contributor data, but a lifecycle rule should be expiring")
            print("    them after a day. Check the rule exists AND is scoped to")
            print(f"    {PREFLIGHT_PREFIX} only -- a rule mis-scoped to raw/ would")
            print("    quietly delete the corpus.")

    print()
    if problems:
        print(f"  {problems} problem(s) found")
    else:
        print("  clean: every row has an object, every object has a row")
    print("=" * 68)
    return 1 if problems else 0


# --- copy ---------------------------------------------------------------


def dump_database(dest: Path, dry_run: bool) -> None:
    """Copy the SQLite file, or pg_dump a Postgres database.

    The database holds the transcripts, the QC verdicts and the consent
    records. Audio with none of those is not a dataset -- it is a pile of WAVs
    you have no legal basis to use.
    """
    url = get_settings().database_url
    parsed = urlparse(url)

    if url.startswith("sqlite"):
        source = Path(url.split("///", 1)[-1])
        if not source.is_file():
            print(f"  database: {source} not found, skipped")
            return
        target = dest / "voice.db"
        print(f"  database: {source.name} -> {target.name} ({human(source.stat().st_size)})")
        if not dry_run:
            # sqlite3 .backup would be safer under concurrent writes, but a
            # file copy is honest about what it is and needs no extra tooling.
            shutil.copy2(source, target)
        return

    if not shutil.which("pg_dump"):
        print("  database: pg_dump not on PATH -- INSTALL postgresql-client")
        print("            the corpus audio alone is not a usable dataset")
        return

    target = dest / "voice.sql"
    print(f"  database: pg_dump {parsed.path.lstrip('/')} -> {target.name}")
    if dry_run:
        return
    with target.open("wb") as fh:
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-privileges", url.replace("+psycopg", "")],
            stdout=fh,
            stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        print(f"  database: pg_dump FAILED -- {result.stderr.decode()[:300]}")


def copy_objects(storage, dest: Path, dry_run: bool) -> tuple[int, int, int]:
    """Incremental pull. Skips anything already present at the same size."""
    copied = skipped = failed = 0
    total_bytes = 0

    for prefix in BACKUP_PREFIXES:
        for key, size in storage.list_keys(prefix):
            target = dest / key
            if target.is_file() and target.stat().st_size == size:
                skipped += 1
                continue

            if dry_run:
                copied += 1
                total_bytes += size
                continue

            try:
                data = storage.get_bytes(key)
            except StorageError as exc:
                print(f"    could not read {key}: {exc}", file=sys.stderr)
                failed += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            # Verify the byte count landed; a short write is worse than none,
            # because it looks like a backup.
            if target.stat().st_size != size:
                print(f"    size mismatch after write: {key}", file=sys.stderr)
                failed += 1
                continue
            copied += 1
            total_bytes += size

    print(f"  objects : {copied} copied ({human(total_bytes)}), {skipped} already current")
    if failed:
        print(f"            {failed} FAILED")
    return copied, skipped, failed


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, help="directory to copy the corpus into")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="audit database rows against stored objects, copy nothing",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dest and not args.verify:
        parser.error("give --dest, --verify, or both")

    storage = get_storage()

    exit_code = 0
    if args.verify:
        exit_code = verify(storage)

    if args.dest:
        dest = args.dest
        print("\n" + "=" * 68)
        print(f"  backup -> {dest}" + ("  (dry run)" if args.dry_run else ""))
        print("=" * 68)
        if not args.dry_run:
            dest.mkdir(parents=True, exist_ok=True)

        copied, skipped, failed = copy_objects(storage, dest, args.dry_run)
        dump_database(dest, args.dry_run)

        if not args.dry_run:
            manifest = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "prefixes": list(BACKUP_PREFIXES),
                "objects_copied": copied,
                "objects_already_current": skipped,
                "objects_failed": failed,
                "note": "derived/ is intentionally excluded; export_dataset.py rebuilds it",
            }
            (dest / "MANIFEST.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            print(f"  manifest: {dest / 'MANIFEST.json'}")

        if failed:
            exit_code = 1

        print("=" * 68)
        print("  This is one copy on one machine. For an offsite second copy:")
        print("    rclone sync r2:voice-corpus/raw b2:voice-corpus-archive/raw")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
