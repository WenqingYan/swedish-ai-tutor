"""Backfill the phrase catalog from saved lessons without API calls."""

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.repositories.phrase_repo import (
    _normalize_phrase,
    is_reviewable_phrase,
)
from swedish_ai_tutor.db.tables import PhraseRecord, UserPhraseProgress


def rebuild_phrases(settings: Settings) -> dict[str, int | str]:
    """Reconcile every locally analyzed phrase while preserving review progress."""
    lesson_paths = sorted(
        path
        for path in settings.lessons_dir.glob("lesson_*.json")
        if ".before-" not in path.name
    )
    if not lesson_paths:
        raise FileNotFoundError(f"No lesson JSON files found in {settings.lessons_dir}")

    backup_path = _backup_database(settings.db_path) if settings.db_path.exists() else None

    phrases: dict[str, dict[str, Any]] = {}
    occurrences: defaultdict[str, int] = defaultdict(int)
    episodes: defaultdict[str, set[int]] = defaultdict(set)
    for path in lesson_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        episode_id = int(data["episode"]["id"])
        stories = data.get("stories") or []
        analyses = (
            [analysis for story in stories for analysis in story.get("analyses", [])]
            if stories
            else data.get("analyses", [])
        )
        for analysis in analyses:
            for raw_phrase in analysis.get("phrases", []):
                key = _normalize_phrase(str(raw_phrase.get("phrase", "")))
                if not is_reviewable_phrase(key):
                    continue
                phrases[key] = {
                    "meaning": str(raw_phrase.get("meaning", "")),
                    "pattern_type": str(raw_phrase.get("pattern_type", "collocation")),
                    "example": {
                        "swedish": str(analysis.get("original", "")),
                        "chinese": str(analysis.get("translation", "")),
                    },
                }
                occurrences[key] += 1
                episodes[key].add(episode_id)

    engine = create_db_engine(settings.db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    created = 0
    updated = 0
    removed = 0
    with factory() as session:
        existing = {record.phrase: record for record in session.scalars(select(PhraseRecord)).all()}
        for phrase, invalid_record in list(existing.items()):
            if is_reviewable_phrase(phrase):
                continue
            has_progress = session.scalar(
                select(UserPhraseProgress.id).where(
                    UserPhraseProgress.phrase_id == invalid_record.id
                )
            )
            if has_progress is None:
                session.delete(invalid_record)
                existing.pop(phrase)
                removed += 1
        for phrase, details in phrases.items():
            record = existing.get(phrase)
            example_json = json.dumps(details["example"], ensure_ascii=False)
            episode_json = json.dumps(sorted(episodes[phrase]))
            if record is None:
                session.add(
                    PhraseRecord(
                        phrase=phrase,
                        meaning=details["meaning"],
                        pattern_type=details["pattern_type"],
                        frequency=occurrences[phrase],
                        examples=example_json,
                        source_episodes=episode_json,
                    )
                )
                created += 1
            else:
                record.meaning = details["meaning"]
                record.pattern_type = details["pattern_type"]
                record.frequency = occurrences[phrase]
                record.examples = example_json
                record.source_episodes = episode_json
                updated += 1
        session.commit()
    return {
        "lesson_files": len(lesson_paths),
        "phrases": len(phrases),
        "created": created,
        "updated": updated,
        "removed": removed,
        "backup": str(backup_path) if backup_path else "",
    }


def _backup_database(db_path: Path) -> Path:
    """Create a consistent SQLite backup before the phrase schema/backfill."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_name(f"{db_path.name}.before-phrases-{stamp}.backup")
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    return backup
