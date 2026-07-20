# v2 — Vocabulary & Review System

## Overview

Build a local vocabulary database with spaced repetition review, integrated with the daily pipeline and accessible via both CLI and Notion.

## User Story

As a Swedish learner, I want all words and phrases I encounter to be automatically tracked, and I want a CLI review system that tests me on due items using spaced repetition, so that I retain vocabulary long-term.

## Functional Requirements

### FR-1: Automatic Vocabulary Collection
- Every word identified in the daily sentence analysis MUST be added to the vocabulary database.
- If a word already exists: increment `frequency`, update `last_seen`.
- If a word is new: create record, set `first_seen`, schedule first review.
- Every phrase identified MUST be stored in the phrase table.
- Every grammar pattern MUST be stored in the grammar table.

### FR-2: Vocabulary Database
- Schema MUST follow `docs/development/vocabulary.md`.
- Full morphology stored as JSON (verb/noun/adjective forms).
- Source episode IDs tracked per word.
- Database is SQLite, stored at `./data/vocabulary.db`.

### FR-3: Spaced Repetition (SM-2)
- Review scheduling uses the SM-2 algorithm.
- Each word has: `ease_factor` (default 2.5), `interval` (days), `next_review` (date).
- After review, learner rates 0–5:
  - 0–2: reset interval to 1 day, reduce ease factor
  - 3: repeat at current interval
  - 4–5: increase interval, adjust ease factor up
- Words never reviewed are treated as "new" cards.

### FR-4: CLI Review Mode
- Command: `python main.py review`
- Shows words/phrases due for review (due date ≤ today).
- Flashcard format: show Swedish → learner recalls → reveal meaning + context → rate (0–5).
- Session ends when no more due items, or user quits.
- Display stats at end: reviewed count, new mastered, failed items.

### FR-5: Manual Word Addition
- Command: `python main.py add-word <word>`
- Looks up morphology via LLM if not provided.
- Adds to database with `frequency = 0` (manually added marker).
- Enters review queue immediately.

### FR-6: Notion Vocabulary View
- A Notion database synced with the local vocabulary.
- Columns: Word, POS, Meaning, Frequency, Last Seen, Mastered, Next Review.
- Sync runs after each daily pipeline + after review sessions.
- Direction: local → Notion (local is source of truth).

## Non-Functional Requirements

### NFR-1: Performance
- CLI review session MUST start within 2 seconds.
- Vocabulary lookup by word MUST be O(log n) (indexed).
- Notion sync MUST handle 50+ word updates without timeout.

### NFR-2: Data Integrity
- Database uses transactions for all writes.
- No word is ever deleted — only deactivated.
- Schema migrations supported via version tracking.

## Acceptance Criteria

1. After running the v1 pipeline, new words appear in the vocabulary DB with correct metadata.
2. `python main.py review` presents due flashcards and updates review state.
3. Re-encountering a word in a later episode increments its frequency.
4. Notion vocabulary database shows current state of all tracked words.
5. `python main.py add-word "kaffe"` adds the word with full morphology.
