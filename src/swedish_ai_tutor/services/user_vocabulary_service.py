"""Per-learner review scheduling over the shared vocabulary catalog."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.tables import UserWordProgress, WordRecord
from swedish_ai_tutor.review.scheduler import ReviewResult, calculate_next_review


class UserVocabularyService:
    """Read and update review state belonging to one learner."""

    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def get_stats(self) -> dict[str, int]:
        """Return shared totals and this learner's progress counts."""
        total = int(self._session.scalar(select(func.count()).select_from(WordRecord)) or 0)
        progress = list(self._session.scalars(
            select(UserWordProgress).where(UserWordProgress.user_id == self._user_id)
        ))
        now = datetime.now(UTC).replace(tzinfo=None)
        mastered = sum(1 for item in progress if item.mastered)
        due = sum(
            1 for item in progress
            if not item.mastered and item.next_review is not None and item.next_review <= now
        )
        new = total - len(progress)
        return {
            "total": total,
            "mastered": mastered,
            "due": due,
            "new": new,
            "learning": len(progress) - mastered,
        }

    def get_review_queue(
        self, limit: int
    ) -> list[tuple[WordRecord, UserWordProgress | None]]:
        """Return this learner's due words first, then unseen shared words."""
        now = datetime.now(UTC).replace(tzinfo=None)
        due = [
            (word, progress)
            for word, progress in self._session.execute(
            select(WordRecord, UserWordProgress)
            .join(UserWordProgress, UserWordProgress.word_id == WordRecord.id)
            .where(UserWordProgress.user_id == self._user_id)
            .where(UserWordProgress.mastered == False)  # noqa: E712
            .where(UserWordProgress.next_review.isnot(None))
            .where(UserWordProgress.next_review <= now)
            .order_by(UserWordProgress.next_review)
            .limit(limit)
            ).all()
        ]
        remaining = limit - len(due)
        if remaining <= 0:
            return due

        progress_exists = select(UserWordProgress.id).where(
            UserWordProgress.user_id == self._user_id,
            UserWordProgress.word_id == WordRecord.id,
        ).exists()
        unseen_words = list(self._session.scalars(
            select(WordRecord)
            .where(~progress_exists)
            .order_by(WordRecord.first_seen.desc())
            .limit(remaining)
        ))
        return [*due, *((word, None) for word in unseen_words)]

    def process_review(self, word_id: int, quality: int) -> ReviewResult:
        """Apply SM-2 only to this learner's state for the shared word."""
        word = self._session.get(WordRecord, word_id)
        if word is None:
            raise ValueError(f"Word ID {word_id} not found")
        progress = self._session.scalar(select(UserWordProgress).where(
            UserWordProgress.user_id == self._user_id,
            UserWordProgress.word_id == word_id,
        ))
        now = datetime.now(UTC).replace(tzinfo=None)
        if progress is not None and (
            progress.next_review is None or progress.next_review > now
        ):
            raise RuntimeError("This word was already reviewed and is not due yet.")

        result = calculate_next_review(
            quality=quality,
            repetitions=progress.repetitions if progress else 0,
            ease_factor=progress.ease_factor if progress else 2.5,
            interval=progress.interval if progress else 0,
        )
        review_time = datetime.now(UTC)
        if progress is None:
            progress = UserWordProgress(
                user_id=self._user_id,
                word_id=word_id,
                first_reviewed_at=review_time,
                last_reviewed_at=review_time,
            )
            self._session.add(progress)
        progress.next_review = result.next_review
        progress.ease_factor = result.ease_factor
        progress.interval = result.interval
        progress.repetitions = result.repetitions
        progress.last_reviewed_at = review_time
        if result.interval > 30 and result.ease_factor > 2.5:
            progress.mastered = True
            progress.next_review = None
        self._session.commit()
        return result
