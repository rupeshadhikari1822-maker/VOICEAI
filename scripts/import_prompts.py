#!/usr/bin/env python
"""Import prompts from JSONL.

    python scripts/import_prompts.py data/prompts_ne.jsonl
    python scripts/import_prompts.py data/prompts_thr.jsonl --lang thr

Nepali prompts activate on import. Everything else lands **inactive**, and has
to be turned on explicitly with --activate after a native speaker has read every
line. That default is deliberate: a machine-translated prompt produces a wrong
transcript, and a wrong transcript is worse for training than no data at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from app.db import SessionLocal, create_all  # noqa: E402
from app.models import Prompt  # noqa: E402

# The seed corpus has been reviewed; other languages have not.
REVIEWED_LANGS = {"ne"}


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSONL file of prompts")
    parser.add_argument("--lang", help="override the lang field on every row")
    parser.add_argument(
        "--activate",
        action="store_true",
        help="mark imported prompts active (only after native-speaker review)",
    )
    parser.add_argument(
        "--update", action="store_true", help="overwrite text of existing prompt ids"
    )
    args = parser.parse_args()

    if not args.path.is_file():
        print(f"error: no such file: {args.path}", file=sys.stderr)
        return 1

    create_all()
    added = updated = skipped = 0
    inactive_langs: set[str] = set()

    with SessionLocal() as db:
        for lineno, line in enumerate(args.path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  line {lineno}: bad JSON, skipped ({exc})", file=sys.stderr)
                skipped += 1
                continue

            text = (row.get("text") or "").strip()
            if not text:
                print(f"  line {lineno}: empty text, skipped", file=sys.stderr)
                skipped += 1
                continue

            lang = args.lang or row.get("lang") or "ne"
            prompt_id = row.get("id") or f"{lang}-{lineno:05d}"
            active = args.activate or lang in REVIEWED_LANGS
            if not active:
                inactive_langs.add(lang)

            existing = db.get(Prompt, prompt_id)
            if existing is not None:
                if args.update:
                    existing.text = text
                    existing.lang = lang
                    existing.category = row.get("category")
                    existing.phonetic_tags = row.get("phonetic_tags")
                    existing.source = row.get("source")
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(
                Prompt(
                    id=prompt_id,
                    lang=lang,
                    text=text,
                    script=row.get("script", "Deva"),
                    category=row.get("category"),
                    phonetic_tags=row.get("phonetic_tags"),
                    source=row.get("source"),
                    active=active,
                )
            )
            added += 1

        db.commit()

    print(f"added {added}, updated {updated}, skipped {skipped}")
    for lang in sorted(inactive_langs):
        print(
            f"\n  '{lang}' prompts imported as INACTIVE and will not be shown.\n"
            f"  Have a native speaker review every sentence, then re-run with --activate."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
