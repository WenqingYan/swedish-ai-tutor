"""Tests for automatic phrase persistence from analyzed lessons."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import PhraseRecord
from swedish_ai_tutor.models.episode import Episode
from swedish_ai_tutor.models.lesson import GrammarNote, Lesson, Phrase, SentenceAnalysis
from swedish_ai_tutor.models.transcript import Transcript
from swedish_ai_tutor.services.phrase_service import PhraseService


def test_lesson_phrases_are_saved_with_bilingual_context(tmp_path: Path) -> None:
    """Every useful analyzed phrase enters the shared phrase catalog."""
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    analysis = SentenceAnalysis(
        original="Regeringen ska ta fram ett nytt förslag.",
        translation="政府将提出一项新建议。",
        grammar=GrammarNote(pattern="ska + infinitiv", explanation="表示计划"),
        phrases=[
            Phrase(
                phrase="ta fram ett förslag",
                meaning="提出一项建议",
                pattern_type="collocation",
            ),
            Phrase(phrase="enligt", meaning="根据"),
        ],
    )
    lesson = Lesson(
        episode=Episode(
            id=321,
            title="Nyheter",
            description="Test",
            publish_date=datetime.now(UTC),
            audio_url="https://example.com/audio.mp3",
            duration_seconds=60,
            url="https://example.com/episode",
        ),
        transcript=Transcript(full_text=analysis.original),
        analyses=[analysis],
    )

    with factory() as session:
        result = PhraseService(session).upsert_from_lesson(lesson)
        records = list(session.scalars(select(PhraseRecord)))

    assert result == {"new_phrases": 1, "updated_phrases": 0}
    assert len(records) == 1
    assert records[0].phrase == "ta fram ett förslag"
    assert json.loads(records[0].examples or "{}") == {
        "swedish": analysis.original,
        "chinese": analysis.translation,
    }
