# Vocabulary Database Schema

## Word Record

| Field | Type | Description |
|-------|------|-------------|
| word | TEXT | Swedish word (base form) |
| pos | TEXT | Part of speech (noun, verb, adj, adv, etc.) |
| frequency | INTEGER | Times encountered across all lessons |
| first_seen | DATE | Date first encountered |
| last_seen | DATE | Date most recently encountered |
| mastered | BOOLEAN | Learner has marked as known |
| next_review | DATE | Next scheduled review date (SM-2) |
| ease_factor | FLOAT | SM-2 ease factor (default 2.5) |
| interval | INTEGER | Current review interval in days |
| examples | TEXT | JSON array of example sentences |
| related_phrases | TEXT | JSON array of phrase IDs |
| synonyms | TEXT | JSON array of synonym words |
| morphology | TEXT | JSON object with full declension/conjugation |
| source_episodes | TEXT | JSON array of episode IDs where word appeared |

## Phrase Record

| Field | Type | Description |
|-------|------|-------------|
| phrase | TEXT | Swedish phrase |
| meaning | TEXT | Chinese meaning |
| frequency | INTEGER | Times encountered |
| first_seen | DATE | — |
| last_seen | DATE | — |
| pattern_type | TEXT | Collocation, idiom, fixed expression, etc. |
| example_sentences | TEXT | JSON array of usage examples |
| related_words | TEXT | JSON array of word IDs |

## Grammar Record

| Field | Type | Description |
|-------|------|-------------|
| pattern_name | TEXT | Descriptive name (e.g., "V2 word order") |
| description | TEXT | Chinese explanation |
| frequency | INTEGER | Times encountered |
| first_seen | DATE | — |
| examples | TEXT | JSON array of sentences demonstrating pattern |
| sfi_relevance | TEXT | How this relates to SFI exam |

## Update Rules

1. **If word exists:** increment frequency, update `last_seen`, recalculate review schedule
2. **If word is new:** create record, set `first_seen` = today, schedule first review
3. **Manual add supported:** CLI command to add words outside the daily pipeline
4. **Never delete:** Words are deactivated, not removed
