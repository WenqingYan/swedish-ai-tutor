"""Tests for sentence timing and listening-player payloads."""

from datetime import UTC, datetime
from pathlib import Path

from swedish_ai_tutor.models.episode import Episode
from swedish_ai_tutor.models.lesson import GrammarNote, Lesson, SentenceAnalysis
from swedish_ai_tutor.models.transcript import Transcript, TranscriptSegment
from swedish_ai_tutor.services.lesson_player import (
    align_analyses,
    lesson_player_payload,
    list_lessons,
    load_lesson,
)


def _analysis(text: str, translation: str = "中文") -> SentenceAnalysis:
    return SentenceAnalysis(
        original=text,
        translation=translation,
        grammar=GrammarNote(pattern="V2", explanation="说明"),
    )


def _lesson() -> Lesson:
    return Lesson(
        episode=Episode(
            id=123,
            title="Lätt svenska",
            description="",
            publish_date=datetime(2026, 8, 8, tzinfo=UTC),
            audio_url="https://audio.test/episode.mp3",
            duration_seconds=30,
            url="https://episode.test/123",
        ),
        transcript=Transcript(
            full_text="I dag regnar det. Men i morgon blir det sol.",
            segments=[
                TranscriptSegment(text="I dag regnar", start=1.2, end=3.0),
                TranscriptSegment(text="det.", start=3.0, end=3.8),
                TranscriptSegment(
                    text="Men i morgon blir det sol.", start=4.0, end=7.5
                ),
            ],
        ),
        analyses=[
            _analysis("I dag regnar det."),
            _analysis("Men i morgon blir det sol."),
        ],
    )


def test_align_analyses_combines_adjacent_segments() -> None:
    lesson = _lesson()

    timings = align_analyses(lesson.all_analyses, lesson.transcript.segments)

    assert timings == [(1.2, 3.8), (4.0, 7.5)]


def test_player_payload_contains_audio_translation_and_timing() -> None:
    payload = lesson_player_payload(_lesson())

    assert payload["audio_url"] == "https://audio.test/episode.mp3"
    assert payload["sentences"][0] == {
        "index": 1,
        "text": "I dag regnar det.",
        "translation": "中文",
        "start": 1.2,
        "end": 3.8,
    }


def test_saved_lessons_can_be_listed_and_loaded(tmp_path: Path) -> None:
    lesson = _lesson()
    path = tmp_path / "lesson_2026-08-08_123.json"
    path.write_text(lesson.model_dump_json(), encoding="utf-8")

    assert list_lessons(tmp_path)[0]["episode_id"] == 123
    assert load_lesson(tmp_path, 123) == lesson
    assert load_lesson(tmp_path, 999) is None
