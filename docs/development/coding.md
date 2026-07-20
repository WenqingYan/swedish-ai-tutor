# Coding Standards

## Python Style

- Python 3.11+ with modern type hints
- All functions must have: docstring, type hints, tests
- Use `pydantic` for data validation and structured models
- Use `dataclasses` for simple internal data structures
- Async where I/O-bound (API calls, file downloads)

## Project Structure

```
src/swedish_ai_tutor/
├── config.py           # Pydantic settings, env loading
├── models/             # Data models (Pydantic + SQLAlchemy)
├── services/           # Business logic (one service per concern)
├── repositories/       # Database access layer
├── exporters/          # Output formatters (Notion, markdown)
├── review/             # Spaced repetition logic
└── prompts/            # External prompt templates
```

## Rules

1. **No duplicated prompts** — One canonical version in `/prompts/`
2. **No hardcoded API keys** — Always from environment or `.env`
3. **No magic strings** — Constants in config or enums
4. **Tests for every service** — Unit tests with mocked dependencies
5. **Structured logging** — Use `logging` module, not print statements
6. **Type-safe API responses** — Parse external API data into Pydantic models immediately

## Dependencies

- Pin exact versions in `pyproject.toml`
- Prefer well-maintained, minimal packages
- Core: `httpx`, `openai`, `pydantic`, `sqlalchemy`, `notion-client`
- Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`

## Error Handling

- API failures: retry with exponential backoff (3 attempts max)
- Transcription failures: log error, skip episode, do not block pipeline
- Notion failures: save lesson locally as JSON fallback, retry on next run
- Database errors: never silently swallow — raise and log
