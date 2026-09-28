"""Tests for token-efficient morphology completion."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import WordRecord
from swedish_ai_tutor.services.morphology_backfill import (
    MorphologyBackfiller,
    backfill_morphology,
    missing_fields,
)


def test_missing_fields_ignores_non_inflecting_parts_of_speech() -> None:
    assert missing_fields("adv", None) == []
    assert missing_fields("verb", {"infinitive": "läsa"}) == [
        "group",
        "imperative",
        "present",
        "past",
        "supine",
    ]


@pytest.mark.asyncio
async def test_batches_only_requested_fields() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {"items": [{"id": 7, "values": {"past": "läste"}}]}
                    )
                )
            )
        ]
    )

    result = await MorphologyBackfiller("test", "test", client=client).fill(
        [{"id": 7, "word": "läsa", "pos": "verb", "missing": ["past"]}]
    )

    assert result == {7: {"past": "läste"}}
    prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert '"meaning":' not in prompt
    assert '"example":' not in prompt


@pytest.mark.asyncio
async def test_backfill_updates_only_incomplete_inflecting_words(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    settings = Settings(
        openai_api_key="test",
        notion_api_key="test",
        notion_parent_page_id="test",
        db_path=db_path,
        data_dir=tmp_path,
    )
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    with factory() as session:
        session.add_all(
            [
                WordRecord(word="snabb", pos="adj", meaning="快", morphology=None),
                WordRecord(word="ofta", pos="adv", meaning="经常", morphology=None),
            ]
        )
        session.commit()

    values = {
        "en_form": "snabb",
        "ett_form": "snabbt",
        "plural_definite": "snabba",
        "comparative": "snabbare",
        "superlative": "snabbast",
    }
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps({"items": [{"id": 1, "values": values}]})
                )
            )
        ]
    )

    result = await backfill_morphology(settings, client=client)

    assert result["words_updated"] == 1
    assert result["api_words"] == 1
    with factory() as session:
        words = session.execute(select(WordRecord).order_by(WordRecord.id)).scalars().all()
        assert json.loads(words[0].morphology or "{}") == values
        assert words[1].morphology is None
