"""Safely merge vocabulary rows that represent the same dictionary word."""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import UserWordProgress, WordRecord
from swedish_ai_tutor.services.vocabulary_normalizer import canonical_word_from_morphology


@dataclass(frozen=True)
class DedupeResult:
    """Summary of one vocabulary deduplication run."""

    merged: int
    renamed: int
    backup_path: Path


def dedupe_vocabulary(db_path: Path) -> DedupeResult:
    """Back up and normalize the database, merging duplicate review cards."""
    if not db_path.exists():
        raise FileNotFoundError(f"Vocabulary database not found: {db_path}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.before-dedupe-{timestamp}.backup")
    shutil.copy2(db_path, backup_path)

    engine = create_db_engine(db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    with factory() as session:
        merged, renamed = _dedupe_session(session)
    return DedupeResult(merged=merged, renamed=renamed, backup_path=backup_path)


def _dedupe_session(session: Session) -> tuple[int, int]:
    """Merge canonical duplicate groups in an open transaction."""
    words = list(session.scalars(select(WordRecord).order_by(WordRecord.id)))
    groups: dict[tuple[str, str], list[WordRecord]] = {}
    for record in words:
        try:
            morphology = json.loads(record.morphology) if record.morphology else None
        except json.JSONDecodeError:
            morphology = None
        key = canonical_word_from_morphology(record.word, record.pos, morphology)
        groups.setdefault(key, []).append(record)

    merged = 0
    renamed = 0
    for (canonical_word, canonical_pos), records in groups.items():
        target = next(
            (
                record
                for record in records
                if record.word.lower() == canonical_word and record.pos == canonical_pos
            ),
            records[0],
        )
        for source in records:
            if source.id == target.id:
                continue
            _merge_word(session, target, source)
            merged += 1
        if target.word != canonical_word or target.pos != canonical_pos:
            target.word = canonical_word
            target.pos = canonical_pos
            renamed += 1
    session.commit()
    return merged, renamed


def _merge_word(session: Session, target: WordRecord, source: WordRecord) -> None:
    """Merge one duplicate into its canonical row without losing learner progress."""
    target.frequency += source.frequency
    target.first_seen = min(target.first_seen, source.first_seen)
    if source.last_seen >= target.last_seen:
        target.last_seen = source.last_seen
        target.examples = source.examples or target.examples
    target.mastered = target.mastered or source.mastered
    target.source_episodes = _merge_episode_json(target.source_episodes, source.source_episodes)
    if (source.repetitions, source.interval) > (target.repetitions, target.interval):
        target.repetitions = source.repetitions
        target.interval = source.interval
        target.ease_factor = source.ease_factor
        target.next_review = source.next_review
    if not target.morphology and source.morphology:
        target.morphology = source.morphology
    if not target.meaning and source.meaning:
        target.meaning = source.meaning

    source_progress = list(
        session.scalars(select(UserWordProgress).where(UserWordProgress.word_id == source.id))
    )
    for progress in source_progress:
        target_progress = session.scalar(
            select(UserWordProgress).where(
                UserWordProgress.user_id == progress.user_id,
                UserWordProgress.word_id == target.id,
            )
        )
        if target_progress is None:
            progress.word_id = target.id
        else:
            if (progress.repetitions, progress.interval) > (
                target_progress.repetitions,
                target_progress.interval,
            ):
                target_progress.mastered = progress.mastered
                target_progress.next_review = progress.next_review
                target_progress.ease_factor = progress.ease_factor
                target_progress.interval = progress.interval
                target_progress.repetitions = progress.repetitions
                target_progress.last_reviewed_at = progress.last_reviewed_at
            target_progress.first_reviewed_at = min(
                target_progress.first_reviewed_at, progress.first_reviewed_at
            )
            target_progress.mastered = target_progress.mastered or progress.mastered
            session.delete(progress)
    session.delete(source)


def _merge_episode_json(first: str | None, second: str | None) -> str | None:
    """Combine stored source episode IDs while preserving their order."""
    values: list[int] = []
    for raw in (first, second):
        try:
            decoded = json.loads(raw or "[]")
        except json.JSONDecodeError:
            decoded = []
        for value in decoded:
            if isinstance(value, int) and value not in values:
                values.append(value)
    return json.dumps(values) if values else None
