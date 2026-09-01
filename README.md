# voice-cloudfrm

A link-based voice recording studio for building a Nepali + minority-language
speech corpus (Tharu, Magar, Newar, Maithili, Bhojpuri, …).

You send one URL. The contributor opens it on a phone or laptop, gives consent,
fills a short profile, passes a microphone check, then reads sentences aloud.
Each clip is uploaded as lossless WAV straight to object storage, with the
metadata written to a database. A single export command turns the whole thing
into a training-ready dataset.

---

## 1. What this system actually has to get right

Most "record your voice" apps fail on data quality, not on UI. Four things
decide whether the corpus is usable for training:

| Requirement | Why it matters | How this repo handles it |
|---|---|---|
| Raw PCM, not Opus/MP3 | Browsers default to `MediaRecorder` → WebM/Opus. Lossy codecs destroy the high-frequency detail vocoders learn from. | Custom `AudioWorklet` captures Float32 PCM and encodes 48 kHz / 16-bit / mono WAV in the browser. |
| Browser DSP switched off | Chrome enables echo cancellation, noise suppression and auto gain by default. AGC pumps the level between sentences and makes a TTS voice sound unstable. | `getUserMedia` constraints explicitly set all three to `false`, and the mic check warns if the browser overrode them. |
| Automatic quality gating | You cannot listen to 40,000 clips by hand. | Every clip gets SNR, peak dBFS, clipping ratio, leading/trailing silence and duration computed client-side and re-verified server-side. Fails are re-recorded on the spot. |
| Speaker + text traceability | A dataset without stable speaker IDs and verified transcripts can't be split or filtered. | Every clip carries `speaker_id` (opaque ULID), `prompt_id`, exact prompt text, and a QC verdict. |

## 2. Architecture

```
                  ┌──────────────────────────────────────────┐
   contributor    │  Browser recorder  (static/)             │
   opens link  ──▶│  AudioWorklet → Float32 → WAV 48k/16/mono│
                  │  live level meter + client-side QC       │
                  └──────────┬───────────────────┬───────────┘
                             │ 1. init           │ 3. PUT wav
                             │ 4. complete       │  (presigned)
                             ▼                   ▼
                  ┌────────────────────┐   ┌──────────────────────┐
                  │ FastAPI  (app/)    │   │ Object storage       │
                  │ sessions, prompts, │──▶│ Cloudflare R2        │
                  │ QC, presigning     │   │ (S3-compatible)      │
                  └─────────┬──────────┘   └──────────┬───────────┘
                            │                         │
                            ▼                         ▼
                  ┌────────────────────┐   ┌──────────────────────┐
                  │ Postgres / SQLite  │   │ scripts/export_...   │
                  │ speakers, clips,   │──▶│ → HF datasets,       │
                  │ consent, prompts   │   │   LJSpeech, Whisper  │
                  └────────────────────┘   └──────────────────────┘
```

Everything is one Python process plus a bucket. No queue, no container
orchestration — that is deliberate, because the bottleneck in this project is
recruiting speakers, not scaling servers.

Audio bytes never pass through the API process. The browser PUTs to a presigned
URL; the server later reads the object back to run QC on what actually landed.

## 3. Storage: use Cloudflare R2

Recommended: **Cloudflare R2**, S3-compatible, no egress fees.

| Provider | Storage | Egress | Notes |
|---|---|---|---|
| **Cloudflare R2** | ~$0.015/GB-mo, 10 GB free tier | **$0** | Best default. You will download this dataset many times during training. |
| Backblaze B2 | ~$0.006/GB-mo | Free via Cloudflare CDN | Cheapest raw storage; good for the cold archive copy. |
| AWS S3 | ~$0.023/GB-mo | ~$0.09/GB | Only if you're already on AWS. Egress will hurt during training runs. |
| Supabase Storage | Bundled with plan | Bundled | Convenient if you also want Supabase Postgres + Auth in one place. |

Sizing, so the cost is concrete: 48 kHz / 16-bit / mono WAV = **345 MB per hour**
of audio. 500 hours ≈ 173 GB ≈ **$2.60/month on R2**. Storage is not your cost
problem; speaker recruitment is.

The storage layer in `app/storage.py` is a thin `boto3` S3 adapter, so R2, B2,
Wasabi, Supabase and local MinIO all work by changing three env vars.

**Object key layout** (never put a name or phone number in a key):

```
raw/{lang}/{speaker_id}/{session_id}/{clip_id}.wav      # 48k master, immutable
derived/16k/{lang}/{speaker_id}/{clip_id}.wav           # ASR training
derived/22k/{lang}/{speaker_id}/{clip_id}.wav           # TTS training
consent/{speaker_id}/consent_{version}.wav              # spoken consent
```

## 4. Audio specification

**Capture (the master you keep forever)**

| Parameter | Value |
|---|---|
| Sample rate | 48 000 Hz (accept 44 100; reject below 32 000) |
| Bit depth | 16-bit signed PCM |
| Channels | Mono |
| Container | WAV (RIFF), uncompressed |
| Peak level | −6 to −3 dBFS |
| Noise floor | below −50 dBFS (target −60) |
| SNR | ≥ 30 dB for ASR, ≥ 40 dB for TTS |
| Clipping | < 0.05 % of samples at full scale |
| Leading/trailing silence | 200–500 ms each |
| Clip length | 2–15 s (sweet spot 4–10 s) |

**Derived sets, generated by `scripts/export_dataset.py`**

- ASR (Whisper / wav2vec2 / MMS): 16 kHz mono WAV
- TTS (VITS / Piper / XTTS): 22 050 Hz mono WAV, loudness-normalised to −23 LUFS
- Never train from a lossy intermediate. Keep the 48 kHz master untouched.

## 5. Recording requirements given to contributors

Shown in the app before the first take, and enforced by the mic check:

- A small, soft room. Bedroom with a bed and curtains beats a large empty hall.
- Windows and doors closed. Fan, AC, cooler and TV switched off.
- Phone on silent — not vibrate. Notifications cause impulse noise.
- Mic 15–20 cm from the mouth, slightly off-axis so plosives don't hit it.
- Wired headset mic is better than a laptop's built-in mic. Bluetooth is
  **rejected**: it resamples to 8/16 kHz mono over HFP.
- No rain, no traffic hour, no other people talking in the room.
- Same room, same mic, same distance across all sessions for one speaker.
- Speak naturally at normal pace. Don't perform, don't read like a newsreader.
- Pause ~0.5 s before starting and after finishing each sentence.

Full version with the Nepali text: `docs/recording-guide.md`.

## 6. Privacy — read this before you collect anything

You are collecting, all at once: a voice biometric, a name, an email, a phone
number, and **caste/ethnicity**. Under Nepal's Individual Privacy Act 2075
(2018), caste and ethnicity are explicitly *sensitive personal information*
(s. 27(2)), and biometric data is protected personal information (s. 2(c)).
Collection requires informed, specific, documented consent, and the data may
only be used for the stated purpose.

Design decisions in this repo that follow from that:

1. **No full street address.** The app asks for province / district /
   municipality / ward. That gives you the dialect-region signal you actually
   need for coverage; a house number gives you liability and nothing else.
2. **Caste and ethnicity are optional**, with an explicit "prefer not to say".
   They are stored separately from the recording metadata and are never written
   into filenames, object keys, or the exported dataset — only a coarse
   `language_variety` field is exported.
3. **Consent is recorded twice**: a checkbox with a timestamped consent version
   plus the SHA-256 of the exact text shown, and an optional spoken consent clip
   stored under `consent/`. That is your documentary proof.
4. **PII stays in the database, never in storage.** The exported dataset carries
   only an opaque `speaker_id`.
5. **A withdrawal path exists.** `scripts/withdraw.py <speaker_id> --confirm`
   deletes the speaker's PII, tombstones the clips and removes the objects.
6. If you plan to publish or sell the dataset, the consent text must say so
   *before* recording. Retro-fitting that consent later is not possible.

The export is built from `Speaker.export_row()`, a fixed list of non-identifying
fields. There is no flag that turns PII back on, and `scripts/smoke_test.py`
asserts that name, email, phone and caste never appear in an export row.

I am not your lawyer. For a dataset you intend to license commercially, have a
Nepali lawyer review `docs/consent-ne.md` before your first session.

## 7. The sentence script

`data/prompts_ne.jsonl` ships with 50 seed Nepali sentences chosen for phonetic
coverage: dental vs retroflex stops, aspirated pairs, ऋ / ज्ञ / क्ष / त्र
conjuncts, nasals, numerals, and question intonation.

50 is a starting point, not a corpus. Targets:

| Goal | Speakers | Sentences each | Audio |
|---|---|---|---|
| Single-speaker TTS voice | 1 | 3 000–8 000 | 10–20 h |
| Multi-speaker TTS | 20–50 | 300–800 | 40–100 h |
| ASR fine-tune (usable) | 200+ | 100–300 | 50–100 h |
| ASR fine-tune (good) | 1 000+ | 100–300 | 300 h+ |

Public sources you can legally draw more text from:

- OpenSLR SLR54 — Nepali text corpus (CC-BY-SA 4.0): <https://openslr.org/54/>
- OpenSLR SLR43 — Nepali TTS corpus, Google/Nepal (CC-BY-SA 4.0): <https://openslr.org/43/>
- Mozilla Common Voice sentence collector (CC0): <https://commonvoice.mozilla.org/sentence-collector>
- Nepali Wikipedia dump (CC-BY-SA): <https://dumps.wikimedia.org/newiki/>

Adding Tharu, Magar or Newar prompts: use `scripts/import_prompts.py`, set the
`lang` field, and **have a native speaker review every sentence before it goes
live**. Unreviewed languages import as `active = false` and are never shown to a
contributor until you pass `--activate`. Do not machine-translate prompts. A bad
prompt produces a bad transcript, and a bad transcript is worse than no data.

## 8. Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # fill in R2 keys
python scripts/init_db.py
python scripts/import_prompts.py data/prompts_ne.jsonl
python scripts/smoke_test.py                           # should print "smoke test passed"
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. For local development with no cloud account,
leave `STORAGE_BACKEND=local` and files land in `./storage_local/`.

Microphone access requires a secure context. On localhost that works; on a real
device you must serve over HTTPS. Use `cloudflared tunnel --url http://localhost:8000`
for a quick public HTTPS link during testing.

### Once you have recordings

```bash
python scripts/qc_report.py                            # hours, pass rate, failure reasons
python scripts/export_dataset.py --format asr --sr 16000 --out export_out/asr
python scripts/export_dataset.py --format tts --sr 22050 --out export_out/tts
python scripts/withdraw.py <speaker_id> --dry-run      # then --confirm
```

Export formats: `asr`, `tts`, `hf` (HuggingFace `datasets`), `ljspeech`. Every
export writes a `DATASET_CARD.md` recording the split seed, speaker counts and
a speaker-disjointness check.

## 9. Roadmap

- [x] Recorder, QC, storage, export
- [ ] Validation UI (a second person listens and approves/rejects clips)
- [ ] Forced alignment (MFA) to catch misreads automatically
- [ ] Speaker dashboard with contribution count
- [ ] Offline PWA mode for field recording without connectivity

Automated QC catches noise and clipping but **cannot catch a misread** — someone
saying the wrong word, cleanly. That is what the validation pass is for, and it
is the most valuable thing to build next. The `clips` table already carries
`verify_status` / `verified_by` / `verified_at`, and `export_dataset.py` already
supports `--verified-only`; what is missing is the `/review` UI.
