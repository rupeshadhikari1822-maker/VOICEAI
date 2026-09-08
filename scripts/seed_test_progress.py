#!/usr/bin/env python
"""Dev/test only: fast-forward a speaker's progress with faked PASSED clips.

    python scripts/seed_test_progress.py <speaker_id> --leave 10

Leaves N of the speaker's remaining active prompts genuinely unrecorded and
fakes a "passed" clip for the rest, so you can finish a real end-to-end test
(mic check -> record a handful for real -> save profile -> done) without
manually recording dozens of sentences first. Faked clips have no real audio
behind their object_key -- they exist only so `GET /api/prompts` skips them.

Refuses to run against a real deployment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.ids import new_ulid  # noqa: E402
from app.models import Clip, Prompt, RecordingSession, Speaker  # noqa: E402


def main() -> int:
    use_utf8()
    if get_settings().is_production:
        print("refusing to run: this is a testing-only tool (ENVIRONMENT=production)", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("speaker_id")
    parser.add_argument("--leave", type=int, default=10, help="prompts to leave genuinely unrecorded")
    args = parser.parse_args()

    with SessionLocal() as db:
        speaker = db.get(Speaker, args.speaker_id)
        if speaker is None:
            print(f"error: no speaker {args.speaker_id!r}", file=sys.stderr)
            return 1

        session = db.scalar(
            select(RecordingSession)
            .where(RecordingSession.speaker_id == speaker.id)
            .order_by(RecordingSession.started_at.desc())
        )
        if session is None:
            print(f"error: speaker {args.speaker_id!r} has no recording session", file=sys.stderr)
            return 1

        already = set(
            db.scalars(
                select(Clip.prompt_id).where(
                    Clip.speaker_id == speaker.id,
                    Clip.qc_status == "passed",
                    Clip.tombstoned.is_(False),
                )
            )
        )
        remaining = db.scalars(
            select(Prompt)
            .where(Prompt.lang == session.lang, Prompt.active.is_(True), Prompt.id.not_in(already))
            .order_by(Prompt.id)
        ).all()

        to_fake = remaining[: max(0, len(remaining) - args.leave)]
        for prompt in to_fake:
            db.add(
                Clip(
                    id=new_ulid(),
                    session_id=session.id,
                    speaker_id=speaker.id,
                    prompt_id=prompt.id,
                    prompt_text=prompt.text,
                    lang=prompt.lang,
                    object_key=f"seed-test/{new_ulid()}.wav",  # no real audio behind this
                    bytes=200_000,
                    qc_status="passed",
                    duration_s=5.0,
                    sample_rate=48000,
                    channels=1,
                    bit_depth=16,
                    snr_db=35.0,
                    peak_dbfs=-5.0,
                    rms_dbfs=-18.0,
                    noise_floor_dbfs=-55.0,
                    clipping_ratio=0.0,
                )
            )
        db.commit()

        print(f"faked {len(to_fake)} passed clip(s) for speaker {speaker.id}")
        print(f"{min(args.leave, len(remaining))} prompt(s) left genuinely unrecorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
