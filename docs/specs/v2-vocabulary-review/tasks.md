# v2 — Implementation Tasks

## Task Order

v2 builds on v1 foundation (database, models, config). Can begin in parallel with v1 Tasks 5+ once T1–T4 are complete.

---

### Task 1: Word Repository

**Goal:** Implement CRUD operations for the vocabulary database.

**Deliverables:**
- `db/repositories/word_repo.py` — full CRUD + query by review date
- `db/repositories/phrase_repo.py` — CRUD for phrases
- `db/repositories/grammar_repo.py` — CRUD for grammar patterns
- Unit tests: insert, update frequency, query due words

**Acceptance:** Can insert words, increment frequency, query by next review date.

---

### Task 2: SM-2 Scheduler

**Goal:** Implement the SM-2 spaced repetition algorithm.

**Deliverables:**
- `review/scheduler.py` — pure function, no side effects
- Unit tests covering all quality ratings (0–5)
- Test: new word → first review at 1 day
- Test: good review → increasing intervals (1, 6, 15, 35...)
- Test: failed review → reset to 1 day

**Acceptance:** All SM-2 state transitions produce correct intervals per the published algorithm.

---

### Task 3: Vocabulary Service

**Goal:** Business logic for word/phrase management with review integration.

**Deliverables:**
- `services/vocabulary_service.py`
- `upsert_word`: create or update with frequency/date tracking
- `update_review`: apply SM-2 after review rating
- `get_due_reviews`: query due items
- `get_statistics`: summary stats
- Unit tests with mocked repository

**Acceptance:** Upserting an existing word increments frequency and updates last_seen without disturbing review state.

---

### Task 4: CLI Review Session

**Goal:** Interactive terminal-based flashcard review.

**Deliverables:**
- `review/session.py` — review loop logic
- `main.py` → `review` CLI command
- Terminal UI: colored output, clear formatting
- Input: rating shortcuts (a/h/g/e → 0/2/3/5)
- Session summary at end
- Test: session flow with mocked input/output

**Acceptance:** Running `python main.py review` presents due items, accepts ratings, and updates database.

---

### Task 5: Manual Word Addition

**Goal:** Let user add words outside the daily pipeline.

**Deliverables:**
- `main.py` → `add-word` CLI command
- Looks up word morphology via LLM (optional, user can skip)
- Inserts into database with `frequency = 0`
- Schedules first review

**Acceptance:** `python main.py add-word "hund"` creates a word record with morphology and review date.

---

### Task 6: Notion Vocabulary Sync

**Goal:** Mirror local vocabulary database to a Notion database.

**Deliverables:**
- `exporters/notion_vocab_sync.py`
- Creates/updates rows in Notion database
- Runs after pipeline completion and after review sessions
- Handles rate limiting (Notion API: 3 req/sec)
- Unit tests with mocked Notion client

**Acceptance:** After running the pipeline, new words appear in the Notion vocabulary database within 1 minute.

---

### Task 7: Pipeline Integration

**Goal:** Connect vocabulary service into the v1 daily pipeline.

**Deliverables:**
- Modify `services/pipeline.py` to call `vocabulary_service.upsert_word()` for each analyzed word
- Modify pipeline to call `notion_vocab_sync.sync_recent()` after page creation
- Integration test: pipeline run → words in database → words in Notion

**Acceptance:** Running the daily pipeline automatically updates vocabulary DB and Notion vocabulary database.

---

## Dependency Graph

```
v1:T4 (database) ──→ T1 (word repository)
                       ├── T2 (SM-2 scheduler) ──→ T3 (vocabulary service)
                       │                              ├── T4 (CLI review)
                       │                              ├── T5 (manual add)
                       │                              └── T7 (pipeline integration)
                       └── T6 (Notion vocab sync) ←── T3
```
