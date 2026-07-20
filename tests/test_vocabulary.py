"""Tests for v2 vocabulary system: SM-2 scheduler, word repo, and vocab service."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.repositories.word_repo import WordRepository
from swedish_ai_tutor.models.lesson import NounMorphology, VocabularyEntry
from swedish_ai_tutor.review.scheduler import calculate_next_review
from swedish_ai_tutor.services.vocabulary_service import VocabularyService

# --- SM-2 Scheduler Tests ---


class TestSM2Scheduler:
    """Test the SM-2 spaced repetition algorithm."""

    def test_first_correct_review_interval_1(self) -> None:
        """First successful review gives interval of 1 day."""
        result = calculate_next_review(quality=4, repetitions=0, ease_factor=2.5, interval=0)
        assert result.interval == 1
        assert result.repetitions == 1

    def test_second_correct_review_interval_6(self) -> None:
        """Second successful review gives interval of 6 days."""
        result = calculate_next_review(quality=4, repetitions=1, ease_factor=2.5, interval=1)
        assert result.interval == 6
        assert result.repetitions == 2

    def test_third_correct_review_grows(self) -> None:
        """Third review interval grows by ease factor."""
        result = calculate_next_review(quality=4, repetitions=2, ease_factor=2.5, interval=6)
        assert result.interval == 15  # round(6 * 2.5) = 15
        assert result.repetitions == 3

    def test_failed_review_resets(self) -> None:
        """Quality < 3 resets repetitions and interval."""
        result = calculate_next_review(quality=1, repetitions=5, ease_factor=2.5, interval=30)
        assert result.interval == 1
        assert result.repetitions == 0

    def test_failed_review_reduces_ease(self) -> None:
        """Failed review reduces ease factor."""
        result = calculate_next_review(quality=0, repetitions=3, ease_factor=2.5, interval=15)
        assert result.ease_factor == 2.3  # 2.5 - 0.2

    def test_ease_factor_minimum(self) -> None:
        """Ease factor never goes below 1.3."""
        result = calculate_next_review(quality=0, repetitions=3, ease_factor=1.3, interval=1)
        assert result.ease_factor == 1.3

    def test_easy_review_increases_ease(self) -> None:
        """Perfect recall increases ease factor."""
        result = calculate_next_review(quality=5, repetitions=3, ease_factor=2.5, interval=10)
        assert result.ease_factor > 2.5

    def test_next_review_is_in_future(self) -> None:
        """Next review date is always in the future."""
        result = calculate_next_review(quality=4, repetitions=0, ease_factor=2.5, interval=0)
        assert result.next_review > datetime.now(UTC)

    def test_invalid_quality_raises(self) -> None:
        """Quality outside 0-5 raises ValueError."""
        with pytest.raises(ValueError, match="Quality must be 0-5"):
            calculate_next_review(quality=6, repetitions=0, ease_factor=2.5, interval=0)


# --- Word Repository Tests ---


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    """Create a test database session."""
    engine = create_db_engine(tmp_path / "test_vocab.db")
    init_db(engine)
    factory = get_session_factory(engine)
    session = factory()
    yield session
    session.close()


class TestWordRepository:
    """Test word repository CRUD operations."""

    def test_create_word(self, db_session: Session) -> None:
        """Create a new word record."""
        repo = WordRepository(db_session)
        record = repo.create(
            word="utreda", pos="verb", meaning="调查",
            morphology={"type": "verb", "group": 2, "present": "utreder"},
            episode_id=123,
        )
        assert record.id is not None
        assert record.word == "utreda"
        assert record.frequency == 1
        assert record.next_review is not None

    def test_get_by_word(self, db_session: Session) -> None:
        """Look up word by name."""
        repo = WordRepository(db_session)
        repo.create(word="hund", pos="noun", meaning="狗")
        found = repo.get_by_word("hund")
        assert found is not None
        assert found.meaning == "狗"

    def test_get_by_word_not_found(self, db_session: Session) -> None:
        """Returns None for unknown word."""
        repo = WordRepository(db_session)
        assert repo.get_by_word("nonexistent") is None

    def test_update_frequency(self, db_session: Session) -> None:
        """Increment frequency and update last_seen."""
        repo = WordRepository(db_session)
        record = repo.create(word="lag", pos="noun", meaning="法律")
        assert record.frequency == 1

        repo.update_frequency(record, episode_id=456)
        assert record.frequency == 2

    def test_get_due_for_review(self, db_session: Session) -> None:
        """Returns words with next_review in the past."""
        repo = WordRepository(db_session)
        record = repo.create(word="förbjuda", pos="verb", meaning="禁止")
        # Set review date to yesterday
        record.next_review = datetime.now(UTC) - timedelta(days=1)
        db_session.commit()

        due = repo.get_due_for_review()
        assert len(due) >= 1
        assert any(w.word == "förbjuda" for w in due)

    def test_get_stats(self, db_session: Session) -> None:
        """Returns correct statistics."""
        repo = WordRepository(db_session)
        repo.create(word="a", pos="noun", meaning="x")
        repo.create(word="b", pos="noun", meaning="y")

        stats = repo.get_stats()
        assert stats["total"] == 2
        assert stats["new"] == 2


# --- Vocabulary Service Tests ---


class TestVocabularyService:
    """Test vocabulary service business logic."""

    def test_upsert_new_word(self, db_session: Session) -> None:
        """Upserting a new word creates it."""
        service = VocabularyService(db_session)
        entry = VocabularyEntry(
            word="telefonförsäljning", pos="noun", meaning="电话推销",
            noun=NounMorphology(
                gender="en",
                indefinite_singular="en telefonförsäljning",
                definite_singular="telefonförsäljningen",
                indefinite_plural="telefonförsäljningar",
                definite_plural="telefonförsäljningarna",
            ),
        )
        record = service.upsert_word(entry, episode_id=100)
        assert record.word == "telefonförsäljning"
        assert record.frequency == 1

    def test_upsert_existing_word_increments(self, db_session: Session) -> None:
        """Upserting an existing word increments frequency."""
        service = VocabularyService(db_session)
        entry = VocabularyEntry(word="brand", pos="noun", meaning="火灾")
        service.upsert_word(entry, episode_id=1)
        service.upsert_word(entry, episode_id=2)

        repo = WordRepository(db_session)
        record = repo.get_by_word("brand", "noun")
        assert record is not None
        assert record.frequency == 2

    def test_process_review_updates_schedule(self, db_session: Session) -> None:
        """Processing a review updates the word's schedule."""
        service = VocabularyService(db_session)
        entry = VocabularyEntry(word="utreda", pos="verb", meaning="调查")
        record = service.upsert_word(entry)

        result = service.process_review(record.id, quality=4)
        assert result.interval == 1
        assert result.repetitions == 1

    def test_get_stats(self, db_session: Session) -> None:
        """Stats reflect current database state."""
        service = VocabularyService(db_session)
        entry1 = VocabularyEntry(word="hund", pos="noun", meaning="狗")
        entry2 = VocabularyEntry(word="katt", pos="noun", meaning="猫")
        service.upsert_word(entry1)
        service.upsert_word(entry2)

        stats = service.get_stats()
        assert stats["total"] == 2
        assert stats["new"] == 2

    def test_add_manual_word(self, db_session: Session) -> None:
        """Manually added word enters the database."""
        service = VocabularyService(db_session)
        record = service.add_manual_word(
            word="kaffe", pos="noun", meaning="咖啡"
        )
        assert record.word == "kaffe"
        assert record.frequency == 1
        assert record.next_review is not None
