# v2 — Design Document

## Architecture Extension

v2 extends v1 by adding persistence and review capabilities. The daily pipeline (v1) feeds into the vocabulary service (v2) automatically.

```
v1 Pipeline
    │
    ▼
┌────────────────────────┐
│  Vocabulary Service    │
│  ├── word_repo         │ ←── CLI: add-word
│  ├── phrase_repo       │
│  └── grammar_repo      │
└───────────┬────────────┘
            │
    ┌───────┴───────┐
    ▼               ▼
┌────────┐    ┌──────────┐
│Review  │    │  Notion  │
│CLI     │    │  Vocab   │
│Session │    │  Sync    │
└────────┘    └──────────┘
```

## Module Design

### 1. Vocabulary Service (`services/vocabulary_service.py`)

**Responsibility:** CRUD operations on words/phrases/grammar with frequency tracking and review scheduling.

**Interface:**
```python
class VocabularyService:
    def upsert_word(self, entry: VocabularyEntry, episode_id: int) -> Word
    def upsert_phrase(self, phrase: Phrase, episode_id: int) -> PhraseRecord
    def add_manual_word(self, word: str) -> Word
    def get_due_reviews(self, date: date = today) -> list[Word]
    def update_review(self, word_id: int, quality: int) -> Word
    def get_statistics(self) -> VocabStats
```

### 2. Word Repository (`db/repositories/word_repo.py`)

```python
class WordRepository:
    def get_by_word(self, word: str) -> Word | None
    def create(self, word: Word) -> Word
    def update(self, word: Word) -> Word
    def get_due_for_review(self, before_date: date) -> list[Word]
    def get_all_active(self) -> list[Word]
    def get_stats(self) -> dict
```

### 3. SM-2 Scheduler (`review/scheduler.py`)

```python
class SM2Scheduler:
    @staticmethod
    def calculate_next_review(
        quality: int,          # 0-5 rating
        repetitions: int,      # number of successful reviews
        ease_factor: float,    # current EF (≥ 1.3)
        interval: int          # current interval in days
    ) -> ReviewResult

class ReviewResult(BaseModel):
    next_review: date
    new_interval: int
    new_ease_factor: float
    new_repetitions: int
```

### 4. Review CLI (`review/session.py`)

**Flow:**
```
1. Load due items (words + phrases)
2. Shuffle
3. For each item:
   a. Display Swedish word/phrase
   b. Wait for user to press Enter (mental recall)
   c. Show: meaning, morphology, example sentence, related phrases
   d. Ask rating (0-5) or shortcuts: (a)gain, (h)ard, (g)ood, (e)asy
   e. Update review state
4. Show session summary
```

### 5. Notion Vocabulary Sync (`exporters/notion_vocab_sync.py`)

**Responsibility:** Keep a Notion database in sync with the local vocabulary DB.

```python
class NotionVocabSync:
    async def sync_all(self) -> SyncResult
    async def sync_word(self, word: Word) -> None
    async def sync_recent(self, since: date) -> SyncResult
```

**Notion database columns:**
| Column | Type | Maps to |
|--------|------|---------|
| Ord (Word) | Title | word.word |
| POS | Select | word.pos |
| Betydelse (Meaning) | Text | word.meaning |
| Frekvens | Number | word.frequency |
| Senast sedd | Date | word.last_seen |
| Nästa repetition | Date | word.next_review |
| Behärskad | Checkbox | word.mastered |
| EF | Number | word.ease_factor |

## Integration with v1 Pipeline

In the v1 pipeline orchestrator, after sentence analysis:

```python
# In pipeline.py, after analysis
for analysis in lesson.analyses:
    for vocab_entry in analysis.vocabulary:
        vocabulary_service.upsert_word(vocab_entry, episode.id)
    for phrase in analysis.phrases:
        vocabulary_service.upsert_phrase(phrase, episode.id)
```

This means v2 code is called by v1's pipeline, but can be developed and tested independently.
