# Review System Requirements

## Philosophy

Review is more important than collection. A word encountered once and never reviewed is a word not learned.

## Spaced Repetition (SM-2 Algorithm)

The system uses the SM-2 algorithm for review scheduling:

1. After each review, the learner rates recall quality (0–5)
2. Ease factor adjusts based on difficulty
3. Interval grows with successful recall
4. Failed items reset to short interval

## Integration Points

1. **Daily pipeline** — Every new word/phrase automatically enters the review queue
2. **CLI review mode** — `python main.py review` presents due items as flashcards
3. **Notion vocabulary database** — Shows words with review status for visual tracking

## Review Triggers

- Every new word: `frequency += 1`, `last_seen = today`, schedule review
- Every known word re-encountered: `frequency += 1`, `last_seen = today`
- Review session: present card → rate → update ease/interval → schedule next

## Priority Rules

1. Failed reviews (interval reset) → highest priority
2. New words (never reviewed) → high priority
3. Due reviews (interval expired) → normal priority
4. Words due soon (within 1 day) → low priority
