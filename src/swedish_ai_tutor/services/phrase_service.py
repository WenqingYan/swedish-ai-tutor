"""Phrase extraction persistence and per-learner review scheduling."""

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.repositories.phrase_repo import (
    PhraseRepository,
    is_automatic_phrase_candidate,
)
from swedish_ai_tutor.db.tables import PhraseRecord, UserPhraseProgress
from swedish_ai_tutor.models.lesson import Lesson
from swedish_ai_tutor.review.scheduler import ReviewResult, calculate_next_review


class PhraseService:
    """Persist all reusable phrases extracted from a lesson."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = PhraseRepository(session)

    def upsert_from_lesson(self, lesson: Lesson) -> dict[str, int]:
        """Write lesson phrases with their original bilingual sentence context."""
        created = 0
        updated = 0
        for analysis in lesson.all_analyses:
            context = {"swedish": analysis.original, "chinese": analysis.translation}
            for phrase in analysis.phrases:
                if not is_automatic_phrase_candidate(phrase.phrase):
                    continue
                _, is_new = self._repo.upsert(
                    phrase.phrase,
                    phrase.meaning,
                    phrase.pattern_type,
                    context,
                    lesson.episode.id,
                )
                created += int(is_new)
                updated += int(not is_new)
        return {"new_phrases": created, "updated_phrases": updated}

    def delete_phrase(self, phrase_id: int) -> str:
        """Delete one shared phrase and every learner's attached progress."""
        record = self._session.get(PhraseRecord, phrase_id)
        if record is None:
            raise ValueError(f"Phrase ID {phrase_id} not found")
        phrase = record.phrase
        self._session.execute(
            delete(UserPhraseProgress).where(
                UserPhraseProgress.phrase_id == phrase_id
            )
        )
        self._session.delete(record)
        self._session.commit()
        return phrase


class UserPhraseService:
    """Review shared phrases using one independent memory curve per learner."""

    def __init__(self, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def get_stats(self) -> dict[str, int]:
        """Return phrase totals and this learner's progress counts."""
        total = int(self._session.scalar(select(func.count()).select_from(PhraseRecord)) or 0)
        progress = list(
            self._session.scalars(
                select(UserPhraseProgress).where(UserPhraseProgress.user_id == self._user_id)
            )
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        mastered = sum(item.mastered for item in progress)
        due = sum(
            not item.mastered and item.next_review is not None and item.next_review <= now
            for item in progress
        )
        return {
            "total": total,
            "mastered": mastered,
            "due": due,
            "new": total - len(progress),
            "learning": len(progress) - mastered,
        }

    def get_review_queue(self, limit: int) -> list[tuple[PhraseRecord, UserPhraseProgress | None]]:
        """Return due phrases first, followed by unseen phrases."""
        now = datetime.now(UTC).replace(tzinfo=None)
        due = [
            (phrase, progress)
            for phrase, progress in self._session.execute(
                select(PhraseRecord, UserPhraseProgress)
                .join(
                    UserPhraseProgress,
                    UserPhraseProgress.phrase_id == PhraseRecord.id,
                )
                .where(UserPhraseProgress.user_id == self._user_id)
                .where(UserPhraseProgress.mastered == False)  # noqa: E712
                .where(UserPhraseProgress.next_review.isnot(None))
                .where(UserPhraseProgress.next_review <= now)
                .order_by(UserPhraseProgress.next_review)
                .limit(limit)
            ).all()
        ]
        remaining = limit - len(due)
        if remaining <= 0:
            return due
        progress_exists = (
            select(UserPhraseProgress.id)
            .where(
                UserPhraseProgress.user_id == self._user_id,
                UserPhraseProgress.phrase_id == PhraseRecord.id,
            )
            .exists()
        )
        unseen = list(
            self._session.scalars(
                select(PhraseRecord)
                .where(~progress_exists)
                .order_by(PhraseRecord.first_seen.desc())
                .limit(remaining)
            )
        )
        return [*due, *((phrase, None) for phrase in unseen)]

    def process_review(self, phrase_id: int, quality: int) -> ReviewResult:
        """Apply SM-2 to one learner's phrase progress."""
        phrase = self._session.get(PhraseRecord, phrase_id)
        if phrase is None:
            raise ValueError(f"Phrase ID {phrase_id} not found")
        progress = self._session.scalar(
            select(UserPhraseProgress).where(
                UserPhraseProgress.user_id == self._user_id,
                UserPhraseProgress.phrase_id == phrase_id,
            )
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        if progress is not None and (progress.next_review is None or progress.next_review > now):
            raise RuntimeError("This phrase was already reviewed and is not due yet.")
        result = calculate_next_review(
            quality=quality,
            repetitions=progress.repetitions if progress else 0,
            ease_factor=progress.ease_factor if progress else 2.5,
            interval=progress.interval if progress else 0,
        )
        review_time = datetime.now(UTC)
        if progress is None:
            progress = UserPhraseProgress(
                user_id=self._user_id,
                phrase_id=phrase_id,
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


def phrase_example(record: PhraseRecord) -> dict[str, str] | None:
    """Decode one phrase's bilingual source sentence."""
    try:
        decoded = json.loads(record.examples or "{}")
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None
