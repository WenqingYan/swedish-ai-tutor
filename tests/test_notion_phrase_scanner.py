"""Tests for low-API import of learner-bolded Notion phrases."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import ArticleRecord, PhraseRecord
from swedish_ai_tutor.services.notion_phrase_scanner import NotionPhraseScanner

PAGE_ID = "3b6367e042638152a17df7bcea50e209"


def _notion_client() -> AsyncMock:
    client = AsyncMock()
    client.search.return_value = {
        "results": [
            {
                "id": PAGE_ID,
                "last_edited_time": "2026-08-08T10:00:00.000Z",
            }
        ],
        "has_more": False,
    }
    client.blocks.children.list.return_value = {
        "results": [
            {
                "id": "block-1",
                "type": "paragraph",
                "has_children": False,
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "Regeringen ska ",
                            "annotations": {"bold": False},
                        },
                        {
                            "plain_text": "ta fram ett förslag",
                            "annotations": {"bold": True},
                        },
                        {
                            "plain_text": " nästa vecka.",
                            "annotations": {"bold": False},
                        },
                    ]
                },
            }
        ],
        "has_more": False,
    }
    return client


def _openai_client() -> AsyncMock:
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"phrases":[{"phrase":"ta fram ett förslag",'
                        '"meaning":"提出一项建议","pattern_type":"collocation",'
                        '"context_chinese":"政府将在下周提出一项建议。"}]}'
                    )
                )
            )
        ]
    )
    return client


@pytest.mark.asyncio
async def test_imports_new_bold_phrase_in_one_batch_and_caches_page(
    tmp_path: Path,
) -> None:
    """One changed page causes one batch; a second unchanged scan causes none."""
    engine = create_db_engine(tmp_path / "vocabulary.db")
    init_db(engine)
    factory = get_session_factory(engine)
    notion = _notion_client()
    openai = _openai_client()
    with factory() as session:
        session.add(
            ArticleRecord(
                episode_id=123,
                title="Nyheter",
                publish_date=datetime.now(UTC),
                audio_url="https://example.com/audio.mp3",
                notion_page_id=f"https://notion.so/Lesson-{PAGE_ID}",
            )
        )
        session.commit()
        scanner = NotionPhraseScanner(
            session,
            "notion-test",
            "openai-test",
            "gpt-4o",
            notion_client=notion,
            openai_client=openai,
        )

        first = await scanner.scan()
        second = await scanner.scan()
        phrase = session.scalar(select(PhraseRecord))

    assert first.imported == 1
    assert first.openai_calls == 1
    assert second.scanned_pages == 0
    assert second.openai_calls == 0
    assert phrase is not None
    assert phrase.meaning == "提出一项建议"
    openai.chat.completions.create.assert_awaited_once()
    assert notion.blocks.children.list.await_count == 1


@pytest.mark.asyncio
async def test_existing_phrase_skips_openai_even_when_page_changed(tmp_path: Path) -> None:
    """Local deduplication happens before any phrase-enrichment request."""
    engine = create_db_engine(tmp_path / "vocabulary.db")
    init_db(engine)
    factory = get_session_factory(engine)
    notion = _notion_client()
    openai = _openai_client()
    with factory() as session:
        session.add_all(
            [
                ArticleRecord(
                    episode_id=123,
                    title="Nyheter",
                    publish_date=datetime.now(UTC),
                    audio_url="https://example.com/audio.mp3",
                    notion_page_id=PAGE_ID,
                ),
                PhraseRecord(
                    phrase="ta fram ett förslag",
                    meaning="提出一项建议",
                    pattern_type="collocation",
                ),
            ]
        )
        session.commit()
        result = await NotionPhraseScanner(
            session,
            "notion-test",
            "openai-test",
            "gpt-4o",
            notion_client=notion,
            openai_client=openai,
        ).scan()

    assert result.already_known == 1
    assert result.imported == 0
    assert result.openai_calls == 0
    openai.chat.completions.create.assert_not_awaited()
