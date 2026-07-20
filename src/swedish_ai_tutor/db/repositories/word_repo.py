"""Repository for managing vocabulary words with frequency and review state."""

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.tables import WordRecord


class WordRepository:
    """Data access layer for vocabulary words.

    Handles word lookup, upsert (create or update frequency),
    and review scheduling queries.
    """

    def __init__(self, session: Session) -> None:
        """Initialize with a database session."""
        self._session = session

    def get_by_word(self, word: str, pos: str | None = None) -> WordRecord | None:
        """Look up a word by its base form, optionally filtered by POS.

        Args:
            word: Swedish word in dictionary form.
            pos: Optional part of speech filter.

        Returns:
            WordRecord or None if not found.
        """
        stmt = select(WordRecord).where(WordRecord.word == word)
        if pos:
            stmt = stmt.where(WordRecord.pos == pos)
        return self._session.execute(stmt).scalar_one_or_none()

    def create(
        self,
        word: str,
        pos: str,
        meaning: str,
        morphology: dict | None = None,  # type: ignore[type-arg]
        episode_id: int | None = None,
    ) -> WordRecord:
        """Create a new word record.

        Args:
            word: Swedish word (base form).
            pos: Part of speech.
            meaning: Chinese meaning.
            morphology: Optional morphology dict (verb/noun/adj forms).
            episode_id: Optional source episode ID.

        Returns:
            The created WordRecord.
        """
        now = datetime.now(UTC)
        # Schedule first review for tomorrow
        from datetime import timedelta

        next_review = now + timedelta(days=1)

        record = WordRecord(
            word=word,
            pos=pos,
            meaning=meaning,
            frequency=1,
            first_seen=now,
            last_seen=now,
            next_review=next_review,
            ease_factor=2.5,
            interval=0,
            repetitions=0,
            morphology=json.dumps(morphology, ensure_ascii=False) if morphology else None,
            source_episodes=json.dumps([episode_id]) if episode_id else None,
        )
        self._session.add(record)
        self._session.commit()
        return record

    def update_frequency(
        self, record: WordRecord, episode_id: int | None = None
    ) -> WordRecord:
        """Increment frequency and update last_seen for an existing word.

        Args:
            record: Existing word record.
            episode_id: Optional episode where word was encountered again.

        Returns:
            Updated WordRecord.
        """
        record.frequency += 1
        record.last_seen = datetime.now(UTC)

        # Add episode to source list
        if episode_id:
            episodes = json.loads(record.source_episodes or "[]")
            if episode_id not in episodes:
                episodes.append(episode_id)
                record.source_episodes = json.dumps(episodes)

        self._session.commit()
        return record

    def update_review(
        self,
        record: WordRecord,
        next_review: datetime,
        ease_factor: float,
        interval: int,
        repetitions: int,
    ) -> WordRecord:
        """Update review scheduling state after a review session.

        Args:
            record: Word record to update.
            next_review: Next scheduled review date.
            ease_factor: Updated ease factor.
            interval: New interval in days.
            repetitions: Updated repetition count.

        Returns:
            Updated WordRecord.
        """
        record.next_review = next_review
        record.ease_factor = ease_factor
        record.interval = interval
        record.repetitions = repetitions
        self._session.commit()
        return record

    def mark_mastered(self, record: WordRecord) -> WordRecord:
        """Mark a word as mastered (removes from review queue).

        Args:
            record: Word to mark as mastered.

        Returns:
            Updated WordRecord.
        """
        record.mastered = True
        record.next_review = None
        self._session.commit()
        return record

    def get_due_for_review(self, before_date: datetime | None = None) -> list[WordRecord]:
        """Get all words due for review.

        Args:
            before_date: Return words with next_review before this date.
                         Defaults to now.

        Returns:
            List of words due for review, ordered by next_review date.
        """
        if before_date is None:
            before_date = datetime.now(UTC)

        stmt = (
            select(WordRecord)
            .where(WordRecord.mastered == False)  # noqa: E712
            .where(WordRecord.next_review.isnot(None))
            .where(WordRecord.next_review <= before_date)
            .order_by(WordRecord.next_review)
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_new_words(self) -> list[WordRecord]:
        """Get words that have never been reviewed (repetitions = 0).

        Returns:
            List of new, unreviewed words.
        """
        stmt = (
            select(WordRecord)
            .where(WordRecord.mastered == False)  # noqa: E712
            .where(WordRecord.repetitions == 0)
            .order_by(WordRecord.first_seen.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_all_active(self) -> list[WordRecord]:
        """Get all non-mastered words.

        Returns:
            List of active words ordered by frequency (highest first).
        """
        stmt = (
            select(WordRecord)
            .where(WordRecord.mastered == False)  # noqa: E712
            .order_by(WordRecord.frequency.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_stats(self) -> dict[str, int]:
        """Get vocabulary statistics.

        Returns:
            Dict with counts: total, mastered, due, new.
        """
        all_words = list(self._session.execute(select(WordRecord)).scalars().all())
        now = datetime.now(UTC).replace(tzinfo=None)  # SQLite stores naive datetimes

        total = len(all_words)
        mastered = sum(1 for w in all_words if w.mastered)
        due = sum(
            1 for w in all_words
            if not w.mastered and w.next_review and w.next_review <= now
        )
        new = sum(1 for w in all_words if not w.mastered and w.repetitions == 0)

        return {
            "total": total,
            "mastered": mastered,
            "due": due,
            "new": new,
            "learning": total - mastered - new,
        }
