# Project: Swedish AI Tutor

## Mission

Build a local AI-assisted Swedish language acquisition system for a single adult learner preparing for SFI C and D levels.

The system transforms authentic Swedish radio news (SR Klartext) into structured daily learning material, delivered as a Notion page every morning.

## Identity

This project IS:
- An AI language acquisition system
- A daily Swedish lesson generator
- A vocabulary and grammar tracker
- An automated learning pipeline

This project is NOT:
- An RSS reader or news aggregator
- A translation tool
- A podcast player or audio app
- A NotebookLM clone
- A multi-user platform

## Core Principles

1. **Learning over consumption** — Every feature must improve language proficiency. News content is raw learning material, not the final product.
2. **Patterns over translation** — Teach reusable language patterns (phrases, verb constructions, collocations) rather than word-by-word meaning.
3. **Review over collection** — Spaced repetition and mastery tracking take priority over accumulating new words.
4. **Automation over manual work** — The system eliminates repetitive tasks. The learner spends time learning, not organizing.

## User Profile

- Single user (no auth, no multi-tenancy)
- Native Chinese speaker learning Swedish
- Preparing for SFI C/D certification
- Runs locally on macOS, with Linux/WSL compatibility
- Uses Notion as primary notebook

## Daily Workflow

```
[launchd trigger — early morning, weekdays]
    ↓
Fetch yesterday's Klartext episode via SR API
    ↓
Download audio (MP3, ~5 min)
    ↓
Transcribe audio → Swedish text (Whisper)
    ↓
Analyze text sentence-by-sentence (LLM)
    ↓
Update local vocabulary database (frequency, review schedule)
    ↓
Generate structured Notion page
    ↓
Learner opens Notion → today's lesson is ready
```

## Success Criteria

A successful milestone delivers:
- Zero manual effort to receive the daily lesson
- Every sentence analyzed with grammar, phrases, vocabulary, and morphology
- Vocabulary tracked with frequency and review scheduling
- Notion page readable and useful for study within 5 minutes of opening
