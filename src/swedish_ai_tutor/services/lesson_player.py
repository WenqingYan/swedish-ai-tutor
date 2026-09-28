"""Build sentence-timed lesson payloads for the listening player."""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from swedish_ai_tutor.models.lesson import Lesson, SentenceAnalysis
from swedish_ai_tutor.models.transcript import TranscriptSegment


def load_lesson(lessons_dir: Path, episode_id: int) -> Lesson | None:
    """Load one saved lesson by its episode identifier."""
    matches = list(lessons_dir.glob(f"lesson_*_{episode_id}.json"))
    if not matches:
        return None
    return Lesson.model_validate_json(matches[-1].read_text(encoding="utf-8"))


def list_lessons(lessons_dir: Path) -> list[dict[str, Any]]:
    """Return saved lessons in reverse chronological order."""
    lessons: list[dict[str, Any]] = []
    for path in sorted(lessons_dir.glob("lesson_*.json"), reverse=True):
        if ".before-" in path.name:
            continue
        try:
            lesson = Lesson.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        lessons.append(
            {
                "episode_id": lesson.episode.id,
                "title": lesson.episode.title,
                "date": lesson.episode.date_str,
                "duration_seconds": lesson.episode.duration_seconds,
                "sentence_count": lesson.sentence_count,
            }
        )
    return lessons


def lesson_player_payload(lesson: Lesson) -> dict[str, Any]:
    """Serialize a lesson with best-effort sentence-level timestamps."""
    analyses = lesson.all_analyses
    timings = align_analyses(analyses, lesson.transcript.segments)
    sentences = []
    for index, (analysis, timing) in enumerate(zip(analyses, timings, strict=True), 1):
        sentences.append(
            {
                "index": index,
                "text": analysis.original,
                "translation": analysis.translation,
                "start": timing[0],
                "end": timing[1],
            }
        )
    return {
        "episode_id": lesson.episode.id,
        "title": lesson.episode.title,
        "date": lesson.episode.date_str,
        "audio_url": lesson.episode.audio_url,
        "duration_seconds": lesson.episode.duration_seconds,
        "sentences": sentences,
    }


def align_analyses(
    analyses: list[SentenceAnalysis], segments: list[TranscriptSegment]
) -> list[tuple[float | None, float | None]]:
    """Align analyzed sentences to ordered spans of Whisper segments."""
    if not segments:
        return [(None, None) for _ in analyses]

    units = _sentence_units(segments)

    cursor = 0
    aligned: list[tuple[float | None, float | None]] = []
    for analysis in analyses:
        target = _normalize(analysis.original)
        best: tuple[float, int, int] | None = None
        for start_index in range(cursor, len(units)):
            combined = ""
            for end_index in range(start_index, min(start_index + 4, len(units))):
                combined = f"{combined} {units[end_index].text}".strip()
                candidate = _normalize(combined)
                score = SequenceMatcher(None, target, candidate).ratio()
                if target in candidate or candidate in target:
                    score += 0.25
                if best is None or score > best[0]:
                    best = (score, start_index, end_index)
            if best is not None and best[0] >= 1.1:
                break

        if best is None or best[0] < 0.42:
            aligned.append((None, None))
            continue
        _, start_index, end_index = best
        aligned.append((units[start_index].start, units[end_index].end))
        cursor = end_index + 1
    return aligned


def _sentence_units(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Split multi-sentence speech segments and estimate their inner timings."""
    units: list[TranscriptSegment] = []
    for segment in segments:
        parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", segment.text)
            if part.strip()
        ]
        if len(parts) <= 1:
            units.append(segment)
            continue
        weights = [max(len(_normalize(part)), 1) for part in parts]
        total_weight = sum(weights)
        duration = max(segment.end - segment.start, 0.0)
        elapsed_weight = 0
        for part, weight in zip(parts, weights, strict=True):
            start = segment.start + duration * elapsed_weight / total_weight
            elapsed_weight += weight
            end = segment.start + duration * elapsed_weight / total_weight
            units.append(
                TranscriptSegment(
                    text=part,
                    start=start,
                    end=end,
                    speaker=segment.speaker,
                )
            )
    return units


def _normalize(text: str) -> str:
    """Normalize Swedish transcript text for fuzzy alignment."""
    return re.sub(r"[^0-9a-zåäö]+", "", text.casefold())
