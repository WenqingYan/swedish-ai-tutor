# v1 — Implementation Tasks

## Task Order

Tasks are ordered by dependency. Each task is independently testable.

---

### Task 1: Project Scaffolding

**Goal:** Set up project structure, dependencies, and dev tooling.

**Deliverables:**
- `pyproject.toml` with all dependencies (pinned versions)
- Directory structure as defined in `docs/development/coding.md`
- `ruff.toml` configuration
- `pytest.ini` or `pyproject.toml` pytest config
- `.env.example` with all required environment variables
- `.gitignore`
- Empty `__init__.py` files

**Acceptance:** `ruff check .` and `mypy .` pass on empty project.

---

### Task 2: Configuration Module

**Goal:** Load and validate all settings from environment.

**Deliverables:**
- `src/swedish_ai_tutor/config.py` with Pydantic `BaseSettings`
- `.env.example` with documented variables
- Unit test: settings load from env vars correctly
- Unit test: missing required keys raise clear error

**Acceptance:** `pytest tests/test_config.py` passes.

---

### Task 3: Data Models

**Goal:** Define all Pydantic models for the pipeline data flow.

**Deliverables:**
- `models/episode.py` — Episode, Transcript, TranscriptSegment
- `models/lesson.py` — Lesson, SentenceAnalysis, VocabularyEntry, GrammarNote, Phrase
- Unit tests: model validation, serialization/deserialization

**Acceptance:** Models can be instantiated with sample data, serialize to JSON, and round-trip.

---

### Task 4: Database Schema + Engine

**Goal:** Set up SQLite database with SQLAlchemy.

**Deliverables:**
- `db/engine.py` — SQLite engine, session factory
- `db/tables.py` — SQLAlchemy table definitions (Word, Phrase, Grammar, Article)
- `db/repositories/article_repo.py` — CRUD for processed articles (deduplication)
- Unit tests: create tables, insert/query articles

**Acceptance:** Database creates successfully, article deduplication works.

---

### Task 5: SR Fetcher Service

**Goal:** Fetch episode metadata and download audio from SR API.

**Deliverables:**
- `services/sr_fetcher.py`
- Parses SR API JSON date format (`/Date(timestamp)/`)
- Filters to most recent episode for target date
- Downloads MP3 to `./data/audio/` directory
- Unit tests with mocked HTTP responses
- Integration test against live SR API (marked as slow)

**Acceptance:** Can fetch today's episode metadata and download audio file.

---

### Task 6: Transcription Service

**Goal:** Transcribe audio to Swedish text via OpenAI Whisper API.

**Deliverables:**
- `services/transcriber.py` — Protocol + WhisperAPITranscriber implementation
- Returns segmented transcript with timestamps
- Unit tests with mocked OpenAI client
- Integration test with real audio file (marked as slow/expensive)

**Acceptance:** 5-minute MP3 produces Swedish text transcription with segments.

---

### Task 7: Prompt Design

**Goal:** Create the sentence analysis prompt template.

**Deliverables:**
- `prompts/v1/sentence_analysis.txt` — Full prompt with `{{sentence}}` placeholder
- Prompt includes JSON output schema instruction
- Prompt follows all rules from `docs/development/prompt.md`
- Test: prompt renders correctly with sample sentence

**Acceptance:** Prompt produces valid structured JSON when tested manually against GPT-4.

---

### Task 8: Sentence Analyzer Service

**Goal:** Send sentences to LLM and parse structured responses.

**Deliverables:**
- `services/sentence_analyzer.py`
- Loads prompt from `/prompts/v1/sentence_analysis.txt`
- Sends to OpenAI with JSON mode
- Parses response into `SentenceAnalysis` model
- Handles LLM refusals, malformed JSON, and timeouts
- Unit tests with mocked LLM responses
- Test with real LLM call (marked as expensive)

**Acceptance:** Swedish sentence → complete SentenceAnalysis object with all fields populated.

---

### Task 9: Notion Exporter

**Goal:** Create formatted Notion pages from lesson data.

**Deliverables:**
- `exporters/notion_exporter.py`
- Creates page in configured Notion parent
- Formats with toggles, tables, headings, callouts
- Deduplication check (don't create page if episode already exported)
- Unit tests with mocked Notion client
- Integration test against real Notion workspace (marked as slow)

**Acceptance:** Lesson data produces a well-formatted, readable Notion page.

---

### Task 10: Pipeline Orchestrator

**Goal:** Wire all services together into the daily pipeline.

**Deliverables:**
- `services/pipeline.py` — orchestrates full flow
- `main.py` — CLI entry point with `run` command
- Saves intermediate results (transcript JSON, analysis JSON) to `./data/`
- Structured logging throughout
- Error handling per design doc strategy
- Integration test with all services mocked

**Acceptance:** `python main.py run` executes full pipeline end-to-end.

---

### Task 11: Cron Setup + Documentation

**Goal:** Make the pipeline run automatically every weekday morning.

**Deliverables:**
- `scripts/setup_cron.sh` — installs cron job
- Cron schedule: weekdays at 07:00 (configurable)
- Log output to `./data/logs/`
- `README.md` with setup instructions

**Acceptance:** Pipeline runs unattended on configured schedule, logs are created.

---

## Dependency Graph

```
T1 (scaffolding)
├── T2 (config)
│   ├── T5 (SR fetcher)
│   ├── T6 (transcriber)
│   └── T8 (sentence analyzer) ← T7 (prompt)
├── T3 (models)
│   └── all services use models
├── T4 (database)
│   └── T10 (pipeline) uses article dedup
└── T9 (Notion exporter)
    └── T10 (pipeline orchestrator)
        └── T11 (cron + docs)
```
