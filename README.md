# Swedish AI Tutor 🇸🇪

**Turn one short Swedish news episode into a complete daily learning routine.**

Swedish AI Tutor is a local-first learning companion for Chinese-speaking SFI
C/D learners. It transforms daily
[Radio Sweden på lätt svenska](https://sverigesradio.se/radioswedenpalattsvenska)
episodes into sentence-by-sentence lessons, builds personal word and phrase
decks, and schedules review according to each learner's memory curve.

Learn on a Mac, review comfortably from an iPhone, and keep the learning
database under your control.

## Why learners use it

- **Real Swedish in context** — learn from current, easy-to-follow news instead
  of isolated textbook sentences.
- **Chinese learning support** — every analyzed sentence, word, phrase, and
  example can include a Chinese explanation.
- **Listening plus speaking** — follow the transcript with synchronized audio,
  slow playback, sentence practice, and guided shadowing pauses.
- **A memory system that stays personal** — words and phrases use date-based
  spaced repetition, so several sessions in one day do not distort the schedule.
- **One shared library, separate progress** — family members can use the same
  content while keeping independent review histories and memory curves.
- **Private by default** — lessons and review data remain on the Mac; private
  iPhone access is available through Tailscale.

## User interface

The mobile-friendly web app is designed for short daily sessions and can be
saved to the iPhone Home Screen like an app.

| Screen | What you can do |
|--------|-----------------|
| **Sign in / accounts** | Keep each learner's review progress separate with password-protected local accounts and secure cookies. |
| **Session start** | Choose **Words** or **Phrases**, select 5, 10, 20, or a custom number of cards, and see what is due before starting. |
| **Word review** | Reveal the Chinese meaning, morphology, and a bilingual sentence from the original news context; rate recall with Again, Hard, Good, or Easy. |
| **Phrase review** | Memorize reusable collocations, sentence frames, particle verbs, and idioms with their original bilingual context. |
| **Listening lessons** | Open a saved episode, follow the highlighted sentence and current word, tap any sentence to seek, change speed, loop a sentence, or hide the Chinese translation. |
| **Shadowing practice** | Listen sentence by sentence, then use the on-screen countdown as dedicated time to repeat aloud before the next sentence plays. |

Unsuitable word and phrase cards can be removed with a deliberately separated,
two-step delete action to reduce accidental taps on mobile.

### A typical 10-minute session

1. Run the daily pipeline on the Mac to collect and analyze the latest lesson.
2. Read the structured lesson in Notion and bold any expression worth keeping.
3. Open the private web app on the iPhone and review today's due cards.
4. Finish with synchronized listening or shadowing practice.
5. Return later for another short session; scheduling still follows calendar
   dates rather than the number of sessions completed.

> This is currently a self-hosted project: you provide your own OpenAI and
> Notion credentials and run the private web service from your Mac.

## What it does

Every weekday morning, this system:

1. **Fetches** yesterday's episode from Sveriges Radio (Radio Sweden på lätt svenska)
2. **Downloads** the audio (MP3, ~9–11 min, 4 news stories)
3. **Transcribes** the audio to Swedish text via OpenAI Whisper
4. **Splits** the transcript into individual news stories
5. **Analyzes** each sentence with GPT-4o (grammar, phrases, vocabulary, morphology)
6. **Saves** all vocabulary to a local SQLite database (frequency + review scheduling)
7. **Creates** a structured Notion page with the day's lesson
8. **Tracks** processed episodes (deduplication)

Each word in the Notion page links to [svenska.se](https://svenska.se) for dictionary lookup.

You can then review learned vocabulary and phrases in the iPhone-friendly web
app or with built-in terminal flashcards using spaced repetition (SM-2).

---

## Commands

### `run` — Daily lesson pipeline

Fetches yesterday's episode and creates a Notion lesson page.

```bash
# Activate virtual environment first
source .venv/bin/activate

# Process all news stories from yesterday's episode
python -m swedish_ai_tutor run

# Only analyze 2 randomly chosen stories (saves cost + time)
python -m swedish_ai_tutor run --news 2

# Only 1 story for a quick daily lesson
python -m swedish_ai_tutor run --news 1
```

### `review` — Flashcard review session

Start an interactive spaced repetition review in the terminal.

```bash
python -m swedish_ai_tutor review          # default: 20 words
python -m swedish_ai_tutor review -n 10    # only 10 words
python -m swedish_ai_tutor review -n 50    # longer session
```

Shows words due for review + up to 5 new words per session:

```
── 1/12 ──
  🇸🇪 utreda [verb]
  (press Enter to reveal)
  🇨🇳 调查
  📝 verb (gr.2): utreda / utreder / utredde / utrett
  📊 freq=3 | interval=6d
  Rate [a/h/g/e/q]: g
```

Rating shortcuts:
- **a** (again) = forgot completely → reset to 1 day
- **h** (hard) = struggled → shorter interval
- **g** (good) = recalled correctly → grow interval
- **e** (easy) = instant recall → grow interval faster
- **q** = quit session

### `web` — Review on iPhone

Start the touch-friendly review app on the Mac. It reviews both words and
reusable phrases from the same lesson database with date-based SM-2 scheduling.

The same private web app provides a sentence-timed listening player at
`/lessons`. It aligns saved lesson sentences with Whisper segments and supports
current-sentence highlighting, click-to-seek, replay, previous/next navigation,
sentence looping, pause-after-sentence practice, and optional Chinese text.
Set `WEB_BASE_URL` to the app's HTTPS Tailscale address to add the player link
to newly generated Notion lesson pages.

The opening screen lets you switch between **Words** and **Phrases**, then choose
5, 10, 20, or a custom number of cards. You can start several sessions in one
day: due cards are always selected first, remaining spaces are filled with new
cards, and a reviewed card cannot advance again until its stored calendar due
date. Words and phrases have separate memory curves.

Word and phrase content is shared between learner accounts, while every account has
its own ease factor, interval, repetitions, next-review date, and mastered
state. Passwords are stored as salted hashes. Sign-in uses an opaque, HTTP-only,
Secure, SameSite cookie; the raw session token is never stored in the database.

After revealing a word, the review card shows its Chinese meaning, morphology,
and then a smaller news-context example with the original Swedish sentence and
Chinese translation. New lessons save this context automatically. Existing
words can be filled from local lesson JSON without API calls by running
`python -m swedish_ai_tutor rebuild-vocab`.

If a word is unsuitable, reveal the card and use **不合适？从词库删除** below
the rating buttons. Deletion requires a separate confirmation and is kept away
from normal review controls to prevent accidental taps. Because the catalog is
shared, confirming permanently removes the word and its review progress for all
local learner accounts.

Phrase review has the same protected flow through **不合适？从短语库删除**.
The action appears only after revealing the phrase, requires a separate
confirmation, and removes the shared phrase plus every learner's attached
phrase-review progress.

Each newly analyzed article now saves its reusable collocations, particle verbs,
fixed expressions, idioms, formal news phrases, and useful SFI sentence frames
to the `phrases` table automatically. Phrase cards show the Chinese meaning,
phrase type, and the original bilingual news context. To import phrases from
all existing local lessons without using API tokens, use the rebuild command
below.

Phrase selection favors expressions that transfer across unrelated subjects,
are conventional or partly non-literal, and are useful to memorize as a single
unit. General frames such as `i vissa fall`, `på grund av`, and
`komma överens om` are prioritized. Transparent topic-only combinations such as
`ha kräftskiva` are left as ordinary vocabulary/context rather than phrase cards.
Automatic verb phrases must use dictionary form (`tycka att`, not
`tycker att`). Manually bolded Notion expressions remain learner-controlled and
are not rejected by this automatic-selection rule.

```bash
python -m swedish_ai_tutor rebuild-phrases
```

### Import bold expressions from Notion

When reading a generated Notion lesson, bold any Swedish multi-word expression
you want to remember. At the beginning of every `run`, the tutor checks its
previously created Notion lesson pages and imports newly bolded expressions into
the shared phrase catalog.

The scan is optimized to minimize API usage:

- one lightweight Notion search normally checks which lesson pages changed;
- unchanged pages are not scanned again;
- single words and invalid text are ignored;
- the local phrase database is checked before any AI request;
- existing phrases are skipped;
- all genuinely new phrases are translated and classified in one batched
  OpenAI request;
- when there are no new phrases, the scan makes zero OpenAI calls.

The surrounding Notion sentence is saved as the phrase's example context. A
temporary Notion or enrichment error does not stop the daily news lesson.

#### 1. Install and connect Tailscale

1. Install [Tailscale for macOS](https://tailscale.com/download/mac) and open
   the app.
2. Sign in and leave the Tailscale menu-bar app connected.
3. Install Tailscale from the App Store on the iPhone, sign in with the same
   account, and connect it.
4. In the Mac app, open **Settings → General → Install Tailscale CLI** and
   approve the administrator prompt.

Open a new Terminal window, or refresh the current shell, then verify the CLI:

```bash
rehash
which tailscale
tailscale status
```

The command path should normally be `/usr/local/bin/tailscale`, and `status`
should list both the Mac and iPhone. If the CLI installation button is not
visible, run the installer included with the app:

```bash
osascript /Applications/Tailscale.app/Contents/Resources/InstallTailscaleCLI.scpt
rehash
```

#### 2. Start the tutor web app

From the project directory:

```bash
cd /Users/wenqingyan/Projects/swedish_ai_tutor_project
.venv/bin/python -m swedish_ai_tutor web
```

Keep this Terminal window open. The server intentionally listens only on
`127.0.0.1:8000`. On the Mac, test it in a browser at
`http://127.0.0.1:8000`. The page loads over local HTTP, but the default Secure
authentication cookie is intended for the Tailscale HTTPS address. For a
temporary Mac-only HTTP test, start the server with
`WEB_SECURE_COOKIES=false`; never use that setting for normal remote access.

#### Keep the Mac awake while serving

For reliable iPhone access, connect the Mac to power and start the tutor with
macOS `caffeinate` instead of the ordinary command:

```bash
cd /Users/wenqingyan/Projects/swedish_ai_tutor_project
caffeinate -i .venv/bin/python -m swedish_ai_tutor web
```

This prevents idle system sleep for as long as the tutor process is running;
the display can still turn off normally. Keep the Terminal window open. Closing
a MacBook lid normally still puts it to sleep, and this command does not restart
the server after a reboot or crash.

For an additional system setting, open **System Settings → Battery → Options**
and enable **Prevent automatic sleeping on power adapter when the display is
off**. Keeping the Mac connected to its power adapter is recommended.

#### 3. Create the private iPhone address

Open a second Terminal window and run:

```bash
tailscale serve --bg http://127.0.0.1:8000
tailscale serve status
```

The final command displays an HTTPS address similar to:

```text
https://your-mac-name.your-tailnet.ts.net
```

Open the complete `https://...ts.net` address in Safari on the iPhone. Do not
enter `127.0.0.1:8000` on the iPhone: that address would refer to the iPhone
itself rather than the Mac.

#### 4. Create the learner accounts

1. Open the Tailscale HTTPS address on your iPhone.
2. On first use, create the owner account. All existing reviewed progress is
   copied to this first account; truly unreviewed words remain new. A timestamped
   `vocabulary.db.before-accounts-*.backup` file is created before this migration.
3. From the session start page, choose **Add account** and create your husband's
   username and password.
4. On his iPhone, open the same Tailscale HTTPS address and sign in with his
   account. He receives the same vocabulary catalog with a fresh, independent
   memory curve.

Each phone keeps its own login cookie. Signing out or rating a word affects only
that account. To use terminal review after accounts exist, identify the learner:

```bash
python -m swedish_ai_tutor review --user your_username
python -m swedish_ai_tutor review --user husband_username
```

When only one account exists, `--user` is optional. When several accounts
exist, the terminal lists the available usernames and requires an explicit
choice.

In Safari, choose **Share → Add to Home Screen → Open as Web App**. Do not use
Tailscale Funnel: `serve` keeps the tutor private to devices in your Tailscale
network.

#### Troubleshooting

- **`zsh: command not found: tailscale`** — Install the CLI from the Tailscale
  Mac app as described above, then open a new Terminal or run `rehash`.
- **`The Tailscale CLI failed to start: Failed to load preferences`** — Open
  the Tailscale Mac app, finish signing in and approving its VPN configuration,
  confirm it shows **Connected**, and retry `tailscale status`.
- **Safari cannot open the address** — Confirm Tailscale is connected on both
  devices, the tutor command is still running, and `tailscale serve status`
  shows the `127.0.0.1:8000` proxy.
- **No words appear** — Confirm `DB_PATH` points to the existing vocabulary
  database and run `python -m swedish_ai_tutor vocab` on the Mac.

The Mac must remain powered on, awake, connected to the internet, and running
the tutor web process while reviewing. To stop the private proxy later, run:

```bash
tailscale serve reset
```

For same-Wi-Fi testing without Tailscale, run `web --host 0.0.0.0` and open the
Mac's local IP address on the iPhone. This exposes the service to the local
network and is not recommended on an untrusted network.

### `vocab` — Show vocabulary statistics

```bash
python -m swedish_ai_tutor vocab
```

```
   📚 Vocabulary Database
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Category         ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total words      │   323 │
│ New (unreviewed) │   280 │
│ Learning         │    43 │
│ Mastered         │     0 │
│ Due for review   │    12 │
└──────────────────┴───────┘
```

### `add-word` — Add and automatically complete vocabulary

Add words you encounter outside the daily pipeline. By default, the command
queries the configured OpenAI API to identify the dictionary form and part of
speech, fill the Chinese meaning and complete verb/noun/adjective forms, and
write a new Swedish example with its Chinese translation. The completed card is
saved directly to the same database used by terminal and web review.

```bash
# Just enter the Swedish word; the API completes the card
python -m swedish_ai_tutor add-word "samhälle"

# Optional hints help when a word is ambiguous
python -m swedish_ai_tutor add-word "utreda" verb "调查"

# Add manually without an API call (no automatic forms or example)
python -m swedish_ai_tutor add-word "samhälle" noun "社会" --no-api
```

The normal command needs a valid `OPENAI_API_KEY` in `.env` and uses a small
amount of API tokens. If enrichment fails, no incomplete word is written; retry
the command or deliberately use `--no-api`.

### `dedupe-vocab` — Merge inflected duplicate cards

Normal lesson imports now use morphology to convert inflected forms to the
dictionary form before checking the database. For example, `berättar` is stored
as `berätta`, `annonserna` as `annons`, and `farligaste` as `farlig`. Common POS
aliases such as `adjective`/`adj` are normalized as well.

To clean duplicates that were added before this behavior was introduced, run:

```bash
python -m swedish_ai_tutor dedupe-vocab
```

The command creates a timestamped database backup first. It combines frequency
and source episodes, keeps the latest example, and preserves the more advanced
review state independently for each local account.

### `rebuild-vocab` — Recheck local lessons and repopulate vocabulary

Reconciles every vocabulary entry in `data/lessons/lesson_*.json` into the
SQLite database. It makes no OpenAI or Notion calls, preserves existing review
progress and manual-only words, fills each lesson word with a Swedish news
sentence and its stored Chinese translation, and creates a timestamped database
backup first.

```bash
python -m swedish_ai_tutor rebuild-vocab
```

### `rebuild-phrases` — Populate phrases from saved lessons

Scans saved lesson JSON, deduplicates phrases, updates frequency and source
episodes, and preserves every learner's phrase-review progress. It makes no API
calls.

```bash
python -m swedish_ai_tutor rebuild-phrases
```

### `dry-run` — Test Notion integration (no OpenAI cost)

Creates a Notion page with realistic mock data. Use this to verify your Notion setup.

```bash
python -m swedish_ai_tutor dry-run
```

---

## Setup

### Prerequisites

- Python 3.11+
- macOS or Linux (Windows WSL is also supported)
- OpenAI account with billing enabled
- Notion account

### 1. Install

```bash
cd swedish_learning_assistant

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the project
pip install -e ".[dev]"
```

On macOS, Python 3.11+ is required (the Apple-provided Python may be older). The
included setup script locates Python 3.11, 3.12, or 3.13 and creates the virtual
environment:

```bash
brew install python@3.12   # only if Python 3.11+ is not already installed
./scripts/setup_macos.sh
source .venv/bin/activate
```

### 2. Get API Keys

#### OpenAI API Key

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create a new secret key (starts with `sk-`)
3. Make sure billing is enabled on your account

#### Notion Integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **New integration**
3. Name it "Swedish AI Tutor", select your workspace
4. Copy the **Internal Integration Secret** (starts with `secret_`)

#### Notion Parent Page ID

1. Create a page in Notion (e.g., "Swedish Learning")
2. Share it with your integration: **...** → **Connections** → find your integration → **Connect**
3. Copy the page ID from the URL:
   ```
   https://www.notion.so/My-Page-abc123def456ghi789jkl012mno345pq
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                    This 32-character hex string is your page ID
   ```

### 3. Configure

Create your `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your real keys:

```env
OPENAI_API_KEY=sk-proj-your-actual-key
NOTION_API_KEY=secret_your-actual-token
NOTION_PARENT_PAGE_ID=your-32-char-hex-id
```

### 4. Test

```bash
# Test Notion connection (free, no OpenAI calls)
python -m swedish_ai_tutor dry-run
```

Check the created page in Notion. If it looks good, you're ready.

### 5. Run

```bash
# Full pipeline (costs ~$0.05-0.15 per run with gpt-4o-mini)
python -m swedish_ai_tutor run

# Or limit to 2 stories
python -m swedish_ai_tutor run --news 2
```

---

## Automate

### macOS (launchd)

macOS uses a per-user LaunchAgent for reliable scheduled execution:

```bash
./scripts/setup_launchd.sh
```

This runs at 07:00 Monday-Friday. Logs are written to
`data/logs/launchd.log` and `data/logs/launchd-error.log`.

### Linux / WSL (cron)

Run the pipeline every weekday morning at 07:00 automatically:

```bash
chmod +x scripts/setup_cron.sh
./scripts/setup_cron.sh
```

This installs a cron job. To verify:
```bash
crontab -l
```

To remove:
```bash
crontab -l | grep -v 'swedish_ai_tutor' | crontab -
```

Logs are saved to `./data/logs/pipeline_YYYY-MM-DD.log`.

---

## Vocabulary & Review System

### How it works

1. **Automatic collection** — every `run` saves all analyzed words to the local SQLite database
2. **Frequency tracking** — words encountered again get frequency +1 and updated `last_seen`
3. **Spaced repetition (SM-2)** — each word has a review schedule that grows with successful recalls:
   - New word → review in 1 day
   - 1st success → 6 days
   - 2nd success → 15 days
   - Continues growing: 35 → 90 → 200+ days
   - Failed → reset to 1 day
4. **Auto-mastery** — words with interval > 30 days and high ease factor are marked as mastered

### Daily workflow

```bash
# Morning: get new lesson (auto-populates vocabulary DB)
python -m swedish_ai_tutor run --news 2

# Anytime: review due words (5-10 min)
python -m swedish_ai_tutor review

# Or review from iPhone through the private web app
python -m swedish_ai_tutor web

# Check progress
python -m swedish_ai_tutor vocab
```

### Database location

The vocabulary database is stored locally at `./data/vocabulary.db` (SQLite). It tracks:

- Word, POS, Chinese meaning
- Full morphology (verb/noun/adjective forms as JSON)
- Latest Swedish news-context sentence and its Chinese translation
- Frequency count (how many times encountered across episodes)
- First seen / last seen dates
- SM-2 state: ease factor, interval, repetitions, next review date
- Source episode IDs
- Mastered flag

---

## Configuration Reference

All settings go in `.env`. Only the first 3 are required:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key for Whisper + GPT |
| `NOTION_API_KEY` | ✅ | — | Notion integration token |
| `NOTION_PARENT_PAGE_ID` | ✅ | — | Notion page to create lessons under |
| `OPENAI_MODEL` | — | `gpt-4o` | LLM model (`gpt-4o-mini` for 15x cheaper) |
| `WHISPER_MODEL` | — | `gpt-4o-transcribe-diarize` | Transcription model; diarization keeps interviewer/interviewee turns |
| `SR_PROGRAM_ID` | — | `4916` | SR program (4916 = Radio Sweden lätt svenska) |
| `MAX_NEWS` | — | `0` | Max stories per lesson (0 = all, 1-4 = random pick) |
| `DATA_DIR` | — | `./data` | Local data directory |
| `DB_PATH` | — | `./data/vocabulary.db` | SQLite database path |
| `LOG_LEVEL` | — | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `WEB_SECURE_COOKIES` | — | `true` | Require HTTPS when storing web login cookies |
| `WEB_BASE_URL` | — | empty | HTTPS/Tailscale base URL for player links in Notion |

---

## Notion Page Format

Each daily lesson page contains:

```
📖 2026-07-13 — Lätt svenska
├── 📻 Episode info (date, duration, clickable audio link)
├── 📝 Description
├── ───────────────
├── 📰 1. Den kritiserade informationsplikten införs
│   ├── [Toggle] 1. Sentence analysis...
│   │   ├── 💬 Chinese translation
│   │   ├── 语法: Grammar pattern + explanation
│   │   ├── 🎓 SFI relevance note
│   │   ├── 短语: Phrases with examples
│   │   ├── 词汇: Vocabulary (linked to svenska.se)
│   │   └── 例句: Example sentence + Chinese translation
│   └── [Toggle] 2. ...
├── ───────────────
├── 📰 2. Mammor får skydd mot våld men inte barnen
│   └── ...
├── ───────────────
└── 📊 Dagens nya ord (vocabulary summary with svenska.se links)
```

---

## Cost

| Component | Cost per episode (gpt-4o-mini) | Cost (gpt-4o) |
|-----------|-------------------------------|---------------|
| Whisper transcription | ~$0.06 | ~$0.06 |
| LLM analysis (batch mode) | ~$0.01–0.03 | ~$0.10–0.30 |
| **Total (all 4 stories)** | **~$0.07–0.09/day** | **~$0.16–0.36/day** |
| **Total (2 stories)** | **~$0.04–0.05/day** | **~$0.08–0.18/day** |

Recommended: set `OPENAI_MODEL=gpt-4o-mini` in `.env` for daily use.

---

## Project Structure

```
swedish_learning_assistant/
├── .env                         # Your API keys (not committed)
├── .env.example                 # Template with placeholder values
├── pyproject.toml               # Dependencies and project config
├── scripts/
│   └── setup_cron.sh           # Cron automation setup
├── data/                        # Runtime data (not committed)
│   ├── audio/                   # Downloaded MP3 files
│   ├── lessons/                 # Saved lesson JSON (debug/fallback)
│   ├── logs/                    # Pipeline execution logs
│   └── vocabulary.db            # SQLite vocabulary database
├── src/swedish_ai_tutor/
│   ├── main.py                  # CLI entry point (run, review, vocab, add-word)
│   ├── __main__.py              # python -m support
│   ├── config.py                # Pydantic settings from .env
│   ├── dry_run.py               # Mock pipeline for testing Notion
│   ├── models/
│   │   ├── episode.py           # SR episode metadata
│   │   ├── transcript.py        # Audio transcription + sentence split
│   │   └── lesson.py            # Lesson, NewsStory, SentenceAnalysis models
│   ├── services/
│   │   ├── sr_fetcher.py        # SR Open API client
│   │   ├── transcriber.py       # Whisper API (Protocol interface)
│   │   ├── sentence_analyzer.py # LLM analysis (batch mode)
│   │   ├── vocabulary_service.py # Word upsert, frequency, review logic
│   │   └── pipeline.py          # Full pipeline orchestrator
│   ├── exporters/
│   │   └── notion_exporter.py   # Lesson → Notion page with blocks
│   ├── db/
│   │   ├── engine.py            # SQLite engine + session factory
│   │   ├── tables.py            # SQLAlchemy table definitions
│   │   └── repositories/
│   │       ├── article_repo.py  # Episode deduplication
│   │       └── word_repo.py     # Vocabulary CRUD + review queries
│   ├── prompts/
│   │   └── v1/
│   │       ├── sentence_analysis.txt       # Single sentence prompt
│   │       └── batch_sentence_analysis.txt # Batch prompt (token-efficient)
│   └── review/
│       ├── scheduler.py         # SM-2 spaced repetition algorithm
│       └── session.py           # CLI flashcard review interface
└── tests/                       # Automated unit and integration tests
    ├── test_config.py
    ├── test_models.py
    ├── test_database.py
    ├── test_sr_fetcher.py
    ├── test_transcriber.py
    ├── test_prompts.py
    ├── test_sentence_analyzer.py
    ├── test_notion_exporter.py
    └── test_vocabulary.py
```

---

## Development

```bash
# Activate venv
source .venv/bin/activate

# Run all checks (linter + types + tests)
ruff check . && mypy src/ && pytest

# Run tests only
pytest

# Run tests with verbose output
pytest -v

# Run a specific test file
pytest tests/test_vocabulary.py

# Lint and auto-fix
ruff check --fix .
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `No module named swedish_ai_tutor` | Activate the venv: `source .venv/bin/activate` |
| `Configuration error` | Check `.env` file exists with all required keys |
| Notion page not created | Run `dry-run` first. Check page is shared with integration |
| `Episode already processed` | Delete `data/vocabulary.db` to reprocess |
| Weekend — no episode | Normal. Episodes only published Mon-Fri |
| OpenAI rate limit | Wait 1 minute and retry. Pipeline has built-in 3x retry |
| High cost | Use `--news 1` or `OPENAI_MODEL=gpt-4o-mini` in `.env` |
| Review shows 0 due | New words become due after 1 day. Check back tomorrow |

---

## Source

**Radio Sweden på lätt svenska** (SR Program ID: 4916)
- URL: [sverigesradio.se/radioswedenpalattsvenska](https://sverigesradio.se/radioswedenpalattsvenska)
- Schedule: Weekdays (Mon-Fri)
- Format: ~9-11 min audio, 4 news stories per episode
- Target: Immigrants learning Swedish
- API: `https://api.sr.se/api/v2/episodes/index?programid=4916&format=json`

---

## Roadmap

- [x] v1: Daily lesson pipeline (SR → Whisper → GPT → Notion)
- [x] News story selection (`--news N` for controlling daily workload)
- [x] News stories with topic headings (visual separation)
- [x] Dictionary links (svenska.se for every word)
- [x] Dry-run mode (test Notion without API cost)
- [x] Batch analysis mode (6 sentences per API call, ~70% token savings)
- [x] v2: Vocabulary database + spaced repetition review (SM-2)
- [x] CLI flashcard review (`review` command)
- [x] Manual word addition (`add-word` command)
- [x] Vocabulary statistics (`vocab` command)
- [ ] v3: Grammar pattern tracking across lessons
- [ ] v4: SFI exercise generation
- [ ] Notion vocabulary database sync
