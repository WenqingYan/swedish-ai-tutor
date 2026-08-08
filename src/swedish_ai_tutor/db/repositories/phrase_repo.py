"""Repository for the shared phrase catalog."""

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.tables import PhraseRecord


class PhraseRepository:
    """Persist reusable phrases and their lesson context."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_phrase(self, phrase: str) -> PhraseRecord | None:
        """Find a phrase using its normalized spelling."""
        normalized = _normalize_phrase(phrase)
        return self._session.scalar(select(PhraseRecord).where(PhraseRecord.phrase == normalized))

    def upsert(
        self,
        phrase: str,
        meaning: str,
        pattern_type: str,
        example: dict[str, str],
        episode_id: int | None,
    ) -> tuple[PhraseRecord, bool]:
        """Create a phrase or update its frequency, source, and latest context."""
        normalized = _normalize_phrase(phrase)
        existing = self.get_by_phrase(normalized)
        now = datetime.now(UTC)
        if existing is not None:
            existing.frequency += 1
            existing.last_seen = now
            if meaning:
                existing.meaning = meaning
            if pattern_type:
                existing.pattern_type = pattern_type
            existing.examples = json.dumps(example, ensure_ascii=False)
            existing.source_episodes = _add_episode(existing.source_episodes, episode_id)
            self._session.commit()
            return existing, False

        record = PhraseRecord(
            phrase=normalized,
            meaning=meaning,
            pattern_type=pattern_type or "collocation",
            examples=json.dumps(example, ensure_ascii=False),
            source_episodes=json.dumps([episode_id]) if episode_id else None,
        )
        self._session.add(record)
        self._session.commit()
        return record, True


def _normalize_phrase(phrase: str) -> str:
    """Normalize whitespace and case for stable phrase deduplication."""
    return " ".join(phrase.strip().lower().split())


def is_reviewable_phrase(phrase: str) -> bool:
    """Reject single words and trivial fragments accidentally labeled as phrases."""
    normalized = _normalize_phrase(phrase)
    return len(normalized.split()) >= 2 and normalized not in {"det är"}


def _add_episode(raw: str | None, episode_id: int | None) -> str | None:
    """Add one episode ID to stored JSON without duplicates."""
    if episode_id is None:
        return raw
    try:
        episodes = json.loads(raw or "[]")
    except json.JSONDecodeError:
        episodes = []
    if episode_id not in episodes:
        episodes.append(episode_id)
    return json.dumps(episodes)
