# v1 — Daily Lesson Pipeline

## Overview

Deliver a fully automated pipeline that transforms yesterday's SR Klartext audio episode into a structured Swedish learning page in Notion every weekday morning.

## User Story

As a Swedish learner, I want yesterday's Klartext episode automatically transformed into a structured learning page in my Notion notebook, so that I can study Swedish every morning without any manual preparation.

## Functional Requirements

### FR-1: Episode Fetching
- The system MUST fetch the latest Klartext episode metadata from SR Open API (program ID: 493).
- The system MUST download the episode audio file (MP3, ~5 min, ~4.8 MB).
- The system MUST skip episodes already processed (deduplication by episode ID).
- The system MUST handle weekends gracefully (no episodes published Sat/Sun).

### FR-2: Audio Transcription
- The system MUST transcribe the downloaded MP3 to Swedish text.
- The system MUST use OpenAI Whisper API (with option to swap for local model later).
- The system SHOULD produce word-level or segment-level timestamps for sentence alignment.
- The system MUST validate transcription is non-empty before proceeding.

### FR-3: Sentence Analysis
- The system MUST split the transcript into individual sentences.
- The system MUST send each sentence to the LLM with the analysis prompt.
- The LLM output MUST follow the structure defined in `docs/development/prompt.md`:
  - Original sentence, Chinese translation, key grammar, key phrases, vocabulary with full morphology, examples, SFI notes.
- The system MUST parse the LLM response into structured data (JSON schema validation).
- The system MUST handle LLM failures gracefully (retry up to 3 times per sentence).

### FR-4: Notion Page Generation
- The system MUST create one Notion page per episode (one page per day).
- The page MUST be created in a configurable Notion database/page.
- The page MUST include:
  - Episode date and title as page title
  - Episode description/summary
  - Link to original audio
  - All analyzed sentences with structured formatting
  - Summary of new vocabulary encountered
- The system MUST format content using appropriate Notion blocks (headings, toggles, tables, callouts).

### FR-5: Pipeline Orchestration
- The system MUST run as a single CLI command: `python main.py run`
- The system MUST be schedulable via cron (non-interactive, no user input required).
- The system MUST log all steps (fetched, transcribed, analyzed, exported).
- The system MUST save intermediate results (transcript, analysis JSON) locally for debugging.
- The system MUST report success/failure clearly in logs.

## Non-Functional Requirements

### NFR-1: Performance
- Full pipeline (fetch → transcribe → analyze → export) MUST complete within 10 minutes.
- Audio download MUST handle network interruptions with retry.

### NFR-2: Cost Efficiency
- Whisper API cost per episode: ~$0.03 (5 min × $0.006/min).
- GPT-4 analysis cost: estimate ~$0.10–0.30 per episode depending on sentence count.
- Total daily cost target: under $0.50.

### NFR-3: Reliability
- Pipeline failure MUST NOT lose already-computed data.
- If Notion upload fails, lesson JSON MUST be saved locally for manual retry.
- If transcription fails, error MUST be logged with episode ID for investigation.

### NFR-4: Security
- API keys (OpenAI, Notion) stored in `.env` file, never committed to git.
- `.env` listed in `.gitignore`.

## Acceptance Criteria

1. Running `python main.py run` with valid API keys produces a Notion page with yesterday's lesson.
2. The Notion page contains all sentences analyzed per the learning material format.
3. Re-running the command for the same date does not create duplicate pages.
4. Pipeline logs show clear progress through each stage.
5. If no new episode exists (weekend), the system exits cleanly with an informative message.
