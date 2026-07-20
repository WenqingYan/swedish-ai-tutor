# Codex Development Guide

## Project mission

Maintain a local AI-assisted Swedish tutor for a Chinese-speaking learner preparing
for SFI C/D. The system turns Radio Sweden på lätt svenska episodes into structured
lessons, persists vocabulary, and schedules spaced-repetition review.

## Working rules

- Use Python 3.11+ with modern type hints, docstrings, and tests.
- Keep services modular and external API responses type-safe.
- Keep prompts versioned under `src/swedish_ai_tutor/prompts/`; never embed secrets.
- Preserve local lesson, audio, log, and database data; these are Git-ignored.
- Run `ruff check .`, `mypy src/`, and `pytest` before handing off changes.
- Use `launchd` for macOS automation and retain cron compatibility for Linux/WSL.
- Keep morphology complete for verbs, nouns, and adjectives; show `—` when source
  lesson data genuinely lacks a form rather than inventing one without authorization.

## Detailed references

- Product and architecture guidance: `docs/development/`
- Historical requirements, designs, and implementation plans: `docs/specs/`
- User setup and command documentation: `README.md`
