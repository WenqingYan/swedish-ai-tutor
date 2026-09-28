"""Token-efficient morphology repair for existing vocabulary cards."""

import json
import shutil
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import WordRecord
from swedish_ai_tutor.models.lesson import VocabularyEntry
from swedish_ai_tutor.prompts import load_prompt, render_prompt
from swedish_ai_tutor.services.vocabulary_service import VocabularyService

FIELDS: dict[str, tuple[str, ...]] = {
    "verb": ("group", "imperative", "infinitive", "present", "past", "supine"),
    "noun": (
        "gender",
        "indefinite_singular",
        "definite_singular",
        "indefinite_plural",
        "definite_plural",
    ),
    "adj": ("en_form", "ett_form", "plural_definite", "comparative", "superlative"),
}


class MorphologyBackfillError(RuntimeError):
    """Raised when a morphology batch cannot be completed safely."""


def missing_fields(pos: str, morphology: dict[str, Any] | None) -> list[str]:
    """Return required morphology fields whose stored values are empty."""
    return [field for field in FIELDS.get(pos.casefold(), ()) if not (morphology or {}).get(field)]


def _decode(record: WordRecord) -> dict[str, Any]:
    if not record.morphology:
        return {}
    try:
        value = json.loads(record.morphology)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _local_morphologies(paths: Iterable[Path]) -> dict[tuple[str, str], dict[str, Any]]:
    """Collect the union of non-empty forms already present in saved lessons."""
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stories = data.get("stories") or []
            analyses = (
                [item for story in stories for item in story.get("analyses", [])]
                if stories
                else data.get("analyses", [])
            )
            for analysis in analyses:
                for raw in analysis.get("vocabulary", []):
                    entry = VocabularyEntry.model_validate(raw)
                    morphology = VocabularyService._build_morphology_dict(entry)  # noqa: SLF001
                    if not morphology:
                        continue
                    key = (entry.word.strip().casefold(), entry.pos.strip().casefold())
                    target = result.setdefault(key, {})
                    for field, value in morphology.items():
                        if value not in (None, ""):
                            target[field] = value
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


class MorphologyBackfiller:
    """Fill only missing morphology, batching compact API requests."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: AsyncOpenAI | None = None,
        batch_size: int = 50,
    ) -> None:
        self._client = client or AsyncOpenAI(api_key=api_key)
        self._model = model
        self._batch_size = batch_size
        self._template = load_prompt("v1", "morphology_backfill")

    async def fill(self, items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        """Return missing field values for all items using compact batches."""
        completed: dict[int, dict[str, Any]] = {}
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            prompt = render_prompt(
                self._template,
                items=json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
            )
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a precise Swedish lexicographer. Return JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                content = response.choices[0].message.content
                parsed = json.loads(content or "")
                returned = {int(item["id"]): item["values"] for item in parsed["items"]}
            except Exception as exc:
                raise MorphologyBackfillError(f"Morphology batch failed: {exc}") from exc

            for source in batch:
                item_id = int(source["id"])
                values = returned.get(item_id)
                if not isinstance(values, dict):
                    raise MorphologyBackfillError(f"API omitted word id {item_id}")
                missing = set(source["missing"])
                if set(values) != missing or any(value in (None, "") for value in values.values()):
                    msg = f"API returned incomplete fields for id {item_id}"
                    raise MorphologyBackfillError(msg)
                completed[item_id] = values
        return completed


async def backfill_morphology(
    settings: Settings, *, client: AsyncOpenAI | None = None
) -> dict[str, Any]:
    """Repair incomplete forms locally first, then use minimal batched API calls."""
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)
    local = _local_morphologies(sorted(settings.lessons_dir.glob("lesson_*.json")))

    with session_factory() as session:
        records = session.execute(select(WordRecord)).scalars().all()
        planned: dict[int, dict[str, Any]] = {}
        api_items: list[dict[str, Any]] = []
        local_fields = 0
        for record in records:
            if record.pos.casefold() not in FIELDS:
                continue
            morphology = _decode(record)
            if not missing_fields(record.pos, morphology):
                continue
            key = (record.word.casefold(), record.pos.casefold())
            for field, value in local.get(key, {}).items():
                if not morphology.get(field) and value not in (None, ""):
                    morphology[field] = value
                    local_fields += 1
            missing = missing_fields(record.pos, morphology)
            planned[record.id] = morphology
            if missing:
                api_items.append(
                    {"id": record.id, "word": record.word, "pos": record.pos, "missing": missing}
                )

        api_values = await MorphologyBackfiller(
            settings.openai_api_key, settings.openai_model, client=client
        ).fill(api_items)
        for item_id, values in api_values.items():
            planned[item_id].update(values)

        backup: Path | None = None
        if planned:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = settings.db_path.with_name(
                f"{settings.db_path.name}.before-morphology-{stamp}.backup"
            )
            shutil.copy2(settings.db_path, backup)
            by_id = {record.id: record for record in records}
            for item_id, morphology in planned.items():
                by_id[item_id].morphology = json.dumps(morphology, ensure_ascii=False)
            session.commit()

    return {
        "words_updated": len(planned),
        "local_fields": local_fields,
        "api_words": len(api_items),
        "api_batches": (len(api_items) + 49) // 50,
        "backup": str(backup) if backup else "",
    }
