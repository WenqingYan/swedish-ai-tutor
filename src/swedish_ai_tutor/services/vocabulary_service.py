"""Vocabulary service — manages word persistence and review scheduling.

Bridges the gap between the LLM analysis output and the vocabulary database.
Called by the pipeline to persist words, and by the review CLI to manage reviews.
"""

import logging

from sqlalchemy.orm import Session

from swedish_ai_tutor.db.repositories.word_repo import WordRepository
from swedish_ai_tutor.db.tables import WordRecord
from swedish_ai_tutor.models.lesson import Lesson, VocabularyEntry
from swedish_ai_tutor.review.scheduler import ReviewResult, calculate_next_review

logger = logging.getLogger(__name__)


class VocabularyService:
    """Business logic for vocabulary management.

    Handles:
    - Upserting words from pipeline analysis
    - Tracking frequency across episodes
    - Processing review ratings
    - Providing statistics
    """

    def __init__(self, session: Session) -> None:
        """Initialize with a database session.

        Args:
            session: SQLAlchemy session.
        """
        self._repo = WordRepository(session)

    def upsert_word(
        self,
        entry: VocabularyEntry,
        episode_id: int | None = None,
        example: dict[str, str] | None = None,
    ) -> WordRecord:
        """Create or update a word from pipeline analysis.

        If the word already exists (same word + pos), increment frequency.
        If new, create with initial review schedule.

        Args:
            entry: VocabularyEntry from sentence analysis.
            episode_id: Source episode ID.
            example: Optional Swedish news sentence and Chinese translation.

        Returns:
            The created or updated WordRecord.
        """
        existing = self._repo.get_by_word(entry.word, entry.pos)

        if existing:
            self._repo.update_frequency(existing, episode_id, example)
            logger.debug("Word updated: %s (freq=%d)", entry.word, existing.frequency)
            return existing

        # Build morphology dict
        morphology = self._build_morphology_dict(entry)

        record = self._repo.create(
            word=entry.word,
            pos=entry.pos,
            meaning=entry.meaning,
            morphology=morphology,
            episode_id=episode_id,
            example=example,
        )
        logger.debug("New word added: %s [%s]", entry.word, entry.pos)
        return record

    def upsert_from_lesson(self, lesson: Lesson) -> dict[str, int]:
        """Persist all vocabulary from a lesson into the database.

        Args:
            lesson: Complete lesson with analyzed sentences.

        Returns:
            Dict with counts: new_words, updated_words.
        """
        new_count = 0
        updated_count = 0
        episode_id = lesson.episode.id

        for analysis in lesson.all_analyses:
            example = {
                "swedish": analysis.original,
                "chinese": analysis.translation,
            }
            for word_entry in analysis.vocabulary:
                existing = self._repo.get_by_word(word_entry.word, word_entry.pos)
                if existing:
                    self._repo.update_frequency(existing, episode_id, example)
                    updated_count += 1
                else:
                    morphology = self._build_morphology_dict(word_entry)
                    self._repo.create(
                        word=word_entry.word,
                        pos=word_entry.pos,
                        meaning=word_entry.meaning,
                        morphology=morphology,
                        episode_id=episode_id,
                        example=example,
                    )
                    new_count += 1

        logger.info(
            "Vocabulary persisted: %d new, %d updated",
            new_count, updated_count,
        )
        return {"new_words": new_count, "updated_words": updated_count}

    def process_review(self, word_id: int, quality: int) -> ReviewResult:
        """Process a review rating for a word.

        Applies the SM-2 algorithm and updates the database.

        Args:
            word_id: ID of the word being reviewed.
            quality: Rating 0-5 from the learner.

        Returns:
            ReviewResult with new scheduling state.

        Raises:
            ValueError: If word not found or quality invalid.
        """
        from sqlalchemy import select

        from swedish_ai_tutor.db.tables import WordRecord

        stmt = select(WordRecord).where(WordRecord.id == word_id)
        session = self._repo._session
        record = session.execute(stmt).scalar_one_or_none()

        if not record:
            msg = f"Word ID {word_id} not found"
            raise ValueError(msg)

        result = calculate_next_review(
            quality=quality,
            repetitions=record.repetitions,
            ease_factor=record.ease_factor,
            interval=record.interval,
        )

        self._repo.update_review(
            record=record,
            next_review=result.next_review,
            ease_factor=result.ease_factor,
            interval=result.interval,
            repetitions=result.repetitions,
        )

        # Mark as mastered if ease factor is high and interval > 30 days
        if result.interval > 30 and result.ease_factor > 2.5:
            self._repo.mark_mastered(record)

        return result

    def get_due_reviews(self) -> list[WordRecord]:
        """Get all words due for review right now.

        Returns:
            List of WordRecords due for review.
        """
        return self._repo.get_due_for_review()

    def get_word(self, word_id: int) -> WordRecord | None:
        """Return one vocabulary record by ID."""
        return self._repo.get_by_id(word_id)

    def get_new_words(self) -> list[WordRecord]:
        """Get words never reviewed.

        Returns:
            List of new WordRecords.
        """
        return self._repo.get_new_words()

    def get_stats(self) -> dict[str, int]:
        """Get vocabulary statistics.

        Returns:
            Dict with total, mastered, due, new, learning counts.
        """
        return self._repo.get_stats()

    def add_manual_word(
        self, word: str, pos: str, meaning: str, morphology: dict | None = None  # type: ignore[type-arg]
    ) -> WordRecord:
        """Manually add a word outside the pipeline.

        Args:
            word: Swedish word (base form).
            pos: Part of speech.
            meaning: Chinese meaning.
            morphology: Optional morphology dict.

        Returns:
            Created WordRecord.
        """
        existing = self._repo.get_by_word(word, pos)
        if existing:
            logger.info("Word already exists: %s (freq=%d)", word, existing.frequency)
            return existing

        record = self._repo.create(
            word=word,
            pos=pos,
            meaning=meaning,
            morphology=morphology,
        )
        logger.info("Manual word added: %s [%s] — %s", word, pos, meaning)
        return record

    def _build_morphology_dict(self, entry: VocabularyEntry) -> dict | None:  # type: ignore[type-arg]
        """Build a JSON-serializable morphology dict from a VocabularyEntry.

        Args:
            entry: Vocabulary entry with optional verb/noun/adjective.

        Returns:
            Dict with morphology data, or None.
        """
        if entry.verb:
            return {
                "type": "verb",
                "group": entry.verb.group,
                "imperative": entry.verb.imperative,
                "infinitive": entry.verb.infinitive,
                "present": entry.verb.present,
                "past": entry.verb.past,
                "supine": entry.verb.supine,
            }
        if entry.noun:
            return {
                "type": "noun",
                "gender": entry.noun.gender,
                "indefinite_singular": entry.noun.indefinite_singular,
                "definite_singular": entry.noun.definite_singular,
                "indefinite_plural": entry.noun.indefinite_plural,
                "definite_plural": entry.noun.definite_plural,
            }
        if entry.adjective:
            return {
                "type": "adjective",
                "en_form": entry.adjective.en_form,
                "ett_form": entry.adjective.ett_form,
                "plural_definite": entry.adjective.plural_definite,
                "comparative": entry.adjective.comparative,
                "superlative": entry.adjective.superlative,
            }
        return None
