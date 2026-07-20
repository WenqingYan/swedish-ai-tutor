# Architecture Constraints

## Runtime Environment

- **Platform:** macOS (Apple Silicon), with Linux/WSL compatibility
- **Execution:** Scheduled launchd user agent on macOS; cron on Linux/WSL
- **Language:** Python 3.11+
- **Database:** SQLite (local file, single user)
- **No web server** — this is a batch pipeline, not a long-running service

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Content source | SR Open API | Public JSON API, no auth |
| Audio transcription | OpenAI Whisper API | Or local whisper model |
| Text analysis | OpenAI GPT API | Configurable provider |
| Vocabulary store | SQLite | Local, persistent |
| Output | Notion API | One page per day |
| Review interface | CLI (local) | Terminal-based flashcards |
| Scheduling | launchd (macOS) / cron (Linux) | Weekday mornings |

## Design Rules

1. **Modular services** — Each service has a single responsibility and can be tested in isolation.
2. **Provider abstraction** — LLM and transcription providers are behind interfaces. Swapping OpenAI for a local model requires changing only the provider implementation.
3. **No hardcoded secrets** — All API keys loaded from environment variables or `.env` file.
4. **Prompts as external files** — Stored in `/prompts/`, versioned, never embedded in code.
5. **Repository pattern** — All database access goes through repository classes.
6. **Fail gracefully** — Pipeline failures are logged and retried. Partial success (e.g., transcription works but Notion upload fails) should not lose data.

## Module Boundaries

```
sr_fetcher       → Downloads episode audio from SR API
transcriber      → Audio → Swedish text
sentence_analyzer → Text → structured learning data (via LLM)
vocabulary_service → Manages word/phrase/grammar DB
notion_exporter  → Lesson → Notion page
review_cli       → Spaced repetition flashcard interface
```

## Future Extensibility

- Additional sources beyond SR Klartext
- Local Whisper model instead of API
- Multiple LLM providers (Anthropic, local LLaMA)
- Notion database for vocabulary view
- SFI exercise generation
- Grammar rule database
