#!/usr/bin/env python
"""Pull candidate reading-prompt sentences from Nepali Wikipedia.

    python scripts/generate_prompts_from_wikipedia.py --target 1500
    python scripts/import_prompts.py data/prompts_ne_wikipedia.jsonl --needs-review

Real, natural Nepali text at scale -- the seed corpus (`data/prompts_ne.jsonl`)
is 50 hand-written placeholder sentences, which is not enough vocabulary
coverage for a real ASR/TTS corpus once more than a handful of people have
recorded against it.

This is extraction, not curation: it fetches random article text and applies
mechanical filters (script, length, punctuation, no digits, deduplication) to
throw out anything that obviously isn't a clean standalone sentence. It cannot
judge whether a sentence that survives filtering actually *reads naturally
aloud*. That is why the output is meant to be imported with
`--needs-review` -- every row lands inactive until a native speaker has
actually read through them, exactly like `import_prompts.py`'s own rule for
any language it doesn't already trust.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._console import use_utf8  # noqa: E402

API_URL = "https://ne.wikipedia.org/w/api.php"
USER_AGENT = "VoiceAI-PromptCollector/1.0 (https://voice.cloudfrm.ai; hello@cloudfrm.ai)"

# Devanagari block + common punctuation/whitespace/digits this script allows
# through. Nepali's own digit script (०-९) is allowed; ASCII digits are not --
# see _looks_clean for why numbers are rejected outright regardless of script.
ALLOWED_CHARS = re.compile(
    r"^[ऀ-ॿ\s।?!,\.;:\"'‘’“”()\-–—]+$"
)
SENTENCE_SPLIT = re.compile(r"(?<=[।?!])\s+")
# Devanagari digits (U+0966-096F) sit inside the allowed script block above,
# so they need their own check: a year or count read aloud varies by speaker
# ("उन्नाइस सय चौध" vs digit-by-digit), the same transcript-consistency problem
# the seed corpus avoids by having no digits in it at all.
DEVANAGARI_DIGITS = re.compile(r"[०-९]")
DISALLOWED_SUBSTRINGS = ("http", "thumb", "px", "==", "{{", "}}", "|", "[", "]")


def fetch_random_extracts(batch_size: int) -> list[str]:
    """Plain-text extracts of `batch_size` random Nepali Wikipedia articles."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "random",
        "grnnamespace": "0",
        "grnlimit": str(batch_size),
        "prop": "extracts",
        "explaintext": "1",
        "exlimit": "max",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    pages = data.get("query", {}).get("pages", {})
    return [p.get("extract", "") for p in pages.values() if p.get("extract")]


def candidate_sentences(extract: str) -> list[str]:
    out = []
    for line in extract.splitlines():
        line = line.strip()
        if not line or line.startswith("="):  # section headings
            continue
        out.extend(s.strip() for s in SENTENCE_SPLIT.split(line) if s.strip())
    return out


def _looks_clean(sentence: str, min_words: int, max_words: int) -> bool:
    if sentence[-1:] not in "।?!":
        return False
    if not ALLOWED_CHARS.match(sentence):
        return False  # any Latin letter, ASCII digit, or stray symbol fails this
    if DEVANAGARI_DIGITS.search(sentence):
        return False
    if any(bad in sentence for bad in DISALLOWED_SUBSTRINGS):
        return False
    words = sentence.split()
    if not (min_words <= len(words) <= max_words):
        return False
    # A lone name/list fragment ending in punctuation still isn't a sentence;
    # require at least one long-ish word as a weak proxy for an actual verb.
    if not any(len(w) >= 4 for w in words):
        return False
    return True


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=1500, help="sentences to collect")
    parser.add_argument("--min-words", type=int, default=4)
    parser.add_argument("--max-words", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=20, help="articles per API call")
    parser.add_argument("--max-requests", type=int, default=400, help="hard stop on API calls")
    parser.add_argument(
        "--out", type=Path, default=Path("data/prompts_ne_wikipedia.jsonl")
    )
    args = parser.parse_args()

    seen: set[str] = set()
    rows: list[dict] = []
    requests_made = 0

    while len(rows) < args.target and requests_made < args.max_requests:
        try:
            extracts = fetch_random_extracts(args.batch_size)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  request {requests_made}: fetch failed, skipping ({exc})", file=sys.stderr)
            extracts = []
        requests_made += 1

        for extract in extracts:
            for sentence in candidate_sentences(extract):
                key = " ".join(sentence.split())
                if key in seen:
                    continue
                if not _looks_clean(sentence, args.min_words, args.max_words):
                    continue
                seen.add(key)
                rows.append(sentence)
                if len(rows) >= args.target:
                    break
            if len(rows) >= args.target:
                break

        print(f"  request {requests_made}: {len(rows)}/{args.target} collected", file=sys.stderr)
        time.sleep(0.3)  # be a polite API citizen

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for i, text in enumerate(rows, 1):
            f.write(
                json.dumps(
                    {
                        "id": f"ne-wiki-{i:05d}",
                        "lang": "ne",
                        "text": text,
                        "script": "Deva",
                        "category": "wikipedia",
                        "source": "ne.wikipedia.org",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"wrote {len(rows)} candidate sentences to {args.out}")
    print("These are UNREVIEWED. Import with --needs-review, then have a native")
    print("speaker read through them before activating any.")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
