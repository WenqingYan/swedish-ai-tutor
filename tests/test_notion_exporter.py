"""Tests for the Notion exporter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from swedish_ai_tutor.exporters.notion_exporter import NotionExporter
from swedish_ai_tutor.models import (
    Episode,
    ExampleSentence,
    GrammarNote,
    Lesson,
    NounMorphology,
    Phrase,
    SentenceAnalysis,
    Transcript,
    VocabularyEntry,
)


@pytest.fixture()
def sample_lesson() -> Lesson:
    """Create a sample lesson for testing."""
    return Lesson(
        episode=Episode(
            id=2838589,
            title="Måndag 13 juli 2026",
            description="Flera döda efter brand / Ny lag om uppehållstillstånd",
            publish_date=datetime(2026, 7, 13, 18, 55, tzinfo=UTC),
            audio_url="https://static-cdn.sr.se/test.mp3",
            duration_seconds=550,
            url="https://www.sverigesradio.se/avsnitt/2838589",
        ),
        transcript=Transcript(
            full_text="Flera döda efter brand. Det var en stor brand."
        ),
        analyses=[
            SentenceAnalysis(
                original="Flera döda efter brand.",
                translation="多人在火灾中死亡。",
                grammar=GrammarNote(
                    pattern="Headline noun phrase",
                    explanation="新闻标题省略动词",
                    sfi_relevance="SFI D阅读理解常见",
                ),
                phrases=[
                    Phrase(
                        phrase="flera döda",
                        meaning="多人死亡",
                        pattern_type="collocation",
                        example="Flera döda i olyckan.",
                    )
                ],
                vocabulary=[
                    VocabularyEntry(
                        word="brand",
                        pos="noun",
                        meaning="火灾",
                        noun=NounMorphology(
                            gender="en",
                            indefinite_singular="en brand",
                            definite_singular="branden",
                            indefinite_plural="bränder",
                            definite_plural="bränderna",
                        ),
                    ),
                ],
                examples=[
                    ExampleSentence(
                        swedish="Flera skadade efter explosionen.",
                        chinese="爆炸后多人受伤。",
                    ),
                ],
                sfi_notes="注意标题风格",
            ),
            SentenceAnalysis(
                original="Det var en stor brand.",
                translation="那是一场大火。",
                grammar=GrammarNote(
                    pattern="Det var + noun phrase",
                    explanation="用det var引导存在句",
                ),
                vocabulary=[
                    VocabularyEntry(word="stor", pos="adj", meaning="大的"),
                ],
            ),
        ],
    )


@pytest.fixture()
def mock_notion_client() -> AsyncMock:
    """Create a mocked Notion client."""
    client = AsyncMock()
    client.pages.create = AsyncMock(return_value={
        "id": "page-id-123",
        "url": "https://notion.so/page-id-123",
    })
    client.blocks.children.append = AsyncMock(return_value={})
    return client


class TestNotionExporter:
    """Test Notion exporter with mocked client."""

    @pytest.mark.asyncio()
    async def test_create_lesson_page(
        self, mock_notion_client: AsyncMock, sample_lesson: Lesson
    ) -> None:
        """Creates a page and returns the URL."""
        exporter = NotionExporter(
            api_key="test",
            parent_page_id="parent-123",
            client=mock_notion_client,
        )
        url = await exporter.create_lesson_page(sample_lesson)

        assert url == "https://notion.so/page-id-123"
        mock_notion_client.pages.create.assert_called_once()

    @pytest.mark.asyncio()
    async def test_page_title_format(
        self, mock_notion_client: AsyncMock, sample_lesson: Lesson
    ) -> None:
        """Page title includes date and program name."""
        exporter = NotionExporter(
            api_key="test",
            parent_page_id="parent-123",
            client=mock_notion_client,
        )
        await exporter.create_lesson_page(sample_lesson)

        call_kwargs = mock_notion_client.pages.create.call_args.kwargs
        title = call_kwargs["properties"]["title"][0]["text"]["content"]
        assert "2026-07-13" in title
        assert "Lätt svenska" in title

    @pytest.mark.asyncio()
    async def test_page_has_parent(
        self, mock_notion_client: AsyncMock, sample_lesson: Lesson
    ) -> None:
        """Page is created under the configured parent."""
        exporter = NotionExporter(
            api_key="test",
            parent_page_id="parent-123",
            client=mock_notion_client,
        )
        await exporter.create_lesson_page(sample_lesson)

        call_kwargs = mock_notion_client.pages.create.call_args.kwargs
        assert call_kwargs["parent"]["page_id"] == "parent-123"

    @pytest.mark.asyncio()
    async def test_page_header_contains_episode_info(
        self, mock_notion_client: AsyncMock, sample_lesson: Lesson
    ) -> None:
        """Page header includes episode info with clickable link."""
        exporter = NotionExporter(
            api_key="test",
            parent_page_id="parent-123",
            client=mock_notion_client,
        )
        await exporter.create_lesson_page(sample_lesson)

        call_kwargs = mock_notion_client.pages.create.call_args.kwargs
        children = call_kwargs["children"]

        # First block should be a callout with episode info
        callouts = [b for b in children if b.get("type") == "callout"]
        assert len(callouts) >= 1

        # Check the callout has rich_text with title
        callout_texts = callouts[0]["callout"]["rich_text"]
        all_text = "".join(t["text"]["content"] for t in callout_texts)
        assert "Måndag 13 juli 2026" in all_text

    @pytest.mark.asyncio()
    async def test_appends_sentence_toggles(
        self, mock_notion_client: AsyncMock, sample_lesson: Lesson
    ) -> None:
        """Appends toggle blocks for sentences after page creation."""
        exporter = NotionExporter(
            api_key="test",
            parent_page_id="parent-123",
            client=mock_notion_client,
        )
        await exporter.create_lesson_page(sample_lesson)

        # blocks.children.append should have been called (for toggles + footer)
        assert mock_notion_client.blocks.children.append.call_count >= 1

    @pytest.mark.asyncio()
    async def test_audio_link_is_clickable(
        self, mock_notion_client: AsyncMock, sample_lesson: Lesson
    ) -> None:
        """The audio link in the header is a proper hyperlink."""
        exporter = NotionExporter(
            api_key="test",
            parent_page_id="parent-123",
            client=mock_notion_client,
        )
        await exporter.create_lesson_page(sample_lesson)

        call_kwargs = mock_notion_client.pages.create.call_args.kwargs
        children = call_kwargs["children"]
        callout = children[0]["callout"]["rich_text"]

        # Find the link element
        link_elements = [t for t in callout if t["text"].get("link")]
        assert len(link_elements) == 1
        assert link_elements[0]["text"]["link"]["url"] == sample_lesson.episode.url
