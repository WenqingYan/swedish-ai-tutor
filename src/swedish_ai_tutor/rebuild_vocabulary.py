"""Repopulate vocabulary from locally saved lesson JSON files without API calls."""

import json
import shutil
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import WordRecord
from swedish_ai_tutor.models.lesson import VocabularyEntry
from swedish_ai_tutor.services.vocabulary_service import VocabularyService


def rebuild_vocabulary(settings: Settings) -> dict[str, int]:
    """Reconcile saved lesson vocabulary into the database, preserving review state."""
    lesson_paths = sorted(settings.lessons_dir.glob("lesson_*.json"))
    if not lesson_paths:
        msg = f"No lesson JSON files found in {settings.lessons_dir}"
        raise FileNotFoundError(msg)

    if settings.db_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = settings.db_path.with_name(f"{settings.db_path.name}.backup_{stamp}")
        shutil.copy2(settings.db_path, backup)
        print(f"Database backup: {backup}")

    # key -> latest entry, occurrence count, episode IDs
    entries: dict[tuple[str, str], VocabularyEntry] = {}
    occurrences: defaultdict[tuple[str, str], int] = defaultdict(int)
    episodes: defaultdict[tuple[str, str], set[int]] = defaultdict(set)

    for path in lesson_paths:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        episode_id = int(data["episode"]["id"])
        stories = data.get("stories") or []
        analyses = (
            [analysis for story in stories for analysis in story.get("analyses", [])]
            if stories
            else data.get("analyses", [])
        )
        for analysis in analyses:
            for raw_entry in analysis.get("vocabulary", []):
                entry = VocabularyEntry.model_validate(raw_entry)
                key = (entry.word.strip().casefold(), entry.pos.strip().casefold())
                entries[key] = entry
                occurrences[key] += 1
                episodes[key].add(episode_id)

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)
    created = 0
    updated = 0

    with session_factory() as session:
        existing_records = session.execute(select(WordRecord)).scalars().all()
        existing = {
            (record.word.strip().casefold(), record.pos.strip().casefold()): record
            for record in existing_records
        }
        morphology_builder = VocabularyService(session)

        for key, entry in entries.items():
            morphology = morphology_builder._build_morphology_dict(entry)
            morphology_json = (
                json.dumps(morphology, ensure_ascii=False) if morphology else None
            )
            episode_json = json.dumps(sorted(episodes[key]))
            record = existing.get(key)
            if record is None:
                now = datetime.now(UTC)
                session.add(
                    WordRecord(
                        word=entry.word,
                        pos=entry.pos,
                        meaning=entry.meaning,
                        frequency=occurrences[key],
                        first_seen=now,
                        last_seen=now,
                        next_review=now + timedelta(days=1),
                        morphology=morphology_json,
                        source_episodes=episode_json,
                    )
                )
                created += 1
            else:
                record.meaning = entry.meaning
                record.frequency = occurrences[key]
                record.morphology = morphology_json
                record.source_episodes = episode_json
                updated += 1

        session.commit()

    return {
        "lesson_files": len(lesson_paths),
        "lesson_words": len(entries),
        "created": created,
        "updated": updated,
        "preserved": len(existing_records) - updated,
    }
