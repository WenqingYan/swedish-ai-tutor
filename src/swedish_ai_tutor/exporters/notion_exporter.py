"""Notion exporter — creates formatted lesson pages in Notion.

Transforms a Lesson into a rich Notion page with toggles, tables,
headings, and callouts for daily Swedish learning.
"""

import logging

from notion_client import AsyncClient as NotionClient

from swedish_ai_tutor.models.lesson import Lesson, SentenceAnalysis, VocabularyEntry

logger = logging.getLogger(__name__)


class NotionExporter:
    """Creates Notion pages from lesson data.

    Produces a structured daily page with episode info, sentence-by-sentence
    analysis in toggle blocks, and a vocabulary summary table.
    """

    def __init__(
        self,
        api_key: str,
        parent_page_id: str,
        client: NotionClient | None = None,
    ) -> None:
        """Initialize the Notion exporter.

        Args:
            api_key: Notion integration API key.
            parent_page_id: ID of the parent page/database to create pages in.
            client: Optional pre-configured Notion client (for testing).
        """
        self._parent_page_id = parent_page_id
        self._client = client or NotionClient(auth=api_key)

    async def create_lesson_page(self, lesson: Lesson) -> str:
        """Create a full lesson page in Notion.

        Handles Notion API limits by:
        - Creating the page with header content first
        - Appending sentence toggles individually (each has nested children)
        - Appending vocabulary summary at the end

        Args:
            lesson: Complete lesson with episode, transcript, and analyses.

        Returns:
            URL of the created Notion page.
        """
        title = f"📖 {lesson.episode.date_str} — Lätt svenska"
        logger.info("Creating Notion page: %s (%d sentences)", title, lesson.sentence_count)

        # Build header blocks (episode info, description, divider, heading)
        header_blocks: list[dict] = []  # type: ignore[type-arg]
        header_blocks.append({
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "📻"},
                "rich_text": [
                    {"type": "text", "text": {"content": f"📋 {lesson.episode.title}\n"}},
                    {"type": "text", "text": {"content": f"📅 {lesson.episode.date_str} | "}},
                    {
                        "type": "text",
                        "text": {"content": f"⏱️ {lesson.episode.duration_seconds}s | "},
                    },
                    {
                        "type": "text",
                        "text": {
                            "content": "🔗 Lyssna här",
                            "link": {"url": lesson.episode.url},
                        },
                    },
                ],
            },
        })
        if lesson.episode.description:
            header_blocks.append(self._paragraph_block(lesson.episode.description))
        header_blocks.append({"type": "divider", "divider": {}})
        header_blocks.append(self._heading_block("🔤 Meningsanalys", level=2))

        # Create page with header only
        response = await self._client.pages.create(
            parent={"page_id": self._parent_page_id},
            properties={
                "title": [{"text": {"content": title}}],
            },
            children=header_blocks,
        )

        page_url = response.get("url", "")
        page_id = response.get("id", "")
        logger.info("Page created, appending %d sentence analyses...", lesson.sentence_count)

        # Append sentence toggles grouped by news story
        sentence_num = 1
        if lesson.stories:
            for story_idx, story in enumerate(lesson.stories, 1):
                # Story topic heading
                story_header: list[dict] = [  # type: ignore[type-arg]
                    {"type": "divider", "divider": {}},
                    self._heading_block(
                        f"📰 {story_idx}. {story.headline}", level=2
                    ),
                ]
                await self._client.blocks.children.append(
                    block_id=page_id, children=story_header,
                )

                # Sentence toggles for this story
                toggle_batch: list[dict] = []  # type: ignore[type-arg]
                for analysis in story.analyses:
                    toggle = self._sentence_toggle(sentence_num, analysis)
                    toggle_batch.append(toggle)
                    sentence_num += 1

                    if len(toggle_batch) >= 5:
                        await self._client.blocks.children.append(
                            block_id=page_id, children=toggle_batch,
                        )
                        toggle_batch = []

                if toggle_batch:
                    await self._client.blocks.children.append(
                        block_id=page_id, children=toggle_batch,
                    )
        else:
            # Fallback: flat list (backward compat with old lesson JSON)
            toggle_batch = []
            for i, analysis in enumerate(lesson.analyses, 1):
                toggle = self._sentence_toggle(i, analysis)
                toggle_batch.append(toggle)

                if len(toggle_batch) >= 5:
                    await self._client.blocks.children.append(
                        block_id=page_id, children=toggle_batch,
                    )
                    toggle_batch = []

            if toggle_batch:
                await self._client.blocks.children.append(
                    block_id=page_id, children=toggle_batch,
                )

        # Append footer: divider + vocabulary summary
        footer_blocks: list[dict] = []  # type: ignore[type-arg]
        footer_blocks.append({"type": "divider", "divider": {}})
        footer_blocks.append(self._heading_block("📊 Dagens nya ord", level=2))
        footer_blocks.extend(self._vocabulary_summary_table(lesson))

        # Split footer if over 100 blocks
        while footer_blocks:
            batch = footer_blocks[:100]
            footer_blocks = footer_blocks[100:]
            await self._client.blocks.children.append(
                block_id=page_id, children=batch,
            )

        logger.info("Notion page complete: %s (id=%s)", page_url, page_id)
        return str(page_url)

    async def page_exists_for_episode(self, episode_id: int) -> bool:
        """Check if a page already exists for this episode.

        Note: This is a simple search — for production use, store the
        mapping in the local database (ArticleRepository).

        Args:
            episode_id: SR episode ID.

        Returns:
            True if a page already exists.
        """
        # We rely on the local ArticleRepository for dedup rather than
        # searching Notion (which is slow and unreliable for this purpose).
        # This method exists for the interface but the pipeline uses the DB.
        _ = episode_id
        return False

    def _build_page_content(self, lesson: Lesson) -> list[dict]:  # type: ignore[type-arg]
        """Build the list of Notion blocks for the page.

        Args:
            lesson: The lesson to render.

        Returns:
            List of Notion block dicts ready for the API.
        """
        blocks: list[dict] = []  # type: ignore[type-arg]

        # Episode info callout
        blocks.append(self._callout_block(
            f"📋 {lesson.episode.title}\n"
            f"📅 {lesson.episode.date_str} | "
            f"⏱️ {lesson.episode.duration_seconds}s | "
            f"🔗 {lesson.episode.url}",
            emoji="📻",
        ))

        # Description
        if lesson.episode.description:
            blocks.append(self._paragraph_block(lesson.episode.description))

        # Divider
        blocks.append({"type": "divider", "divider": {}})

        # Section: Sentences
        blocks.append(self._heading_block("🔤 Meningsanalys", level=2))

        # Each sentence in a toggle block
        for i, analysis in enumerate(lesson.analyses, 1):
            toggle = self._sentence_toggle(i, analysis)
            blocks.append(toggle)

        # Divider
        blocks.append({"type": "divider", "divider": {}})

        # Section: Vocabulary summary
        blocks.append(self._heading_block("📊 Dagens nya ord", level=2))
        vocab_table = self._vocabulary_summary_table(lesson)
        blocks.extend(vocab_table)

        return blocks

    def _sentence_toggle(
        self, index: int, analysis: SentenceAnalysis
    ) -> dict:  # type: ignore[type-arg]
        """Create a toggle block for one sentence analysis.

        Args:
            index: Sentence number.
            analysis: The sentence analysis data.

        Returns:
            Toggle block dict with children.
        """
        # Toggle title: the Swedish sentence
        title_text = f"{index}. {analysis.original}"

        children: list[dict] = []  # type: ignore[type-arg]

        # Translation
        children.append(self._callout_block(
            f"🇨🇳 {analysis.translation}", emoji="💬"
        ))

        # Grammar
        children.append(self._heading_block("语法", level=3))
        children.append(self._paragraph_block(
            f"**{analysis.grammar.pattern}**\n{analysis.grammar.explanation}"
        ))
        if analysis.grammar.sfi_relevance:
            children.append(self._callout_block(
                f"📝 SFI: {analysis.grammar.sfi_relevance}", emoji="🎓"
            ))

        # Phrases
        if analysis.phrases:
            children.append(self._heading_block("短语", level=3))
            for phrase in analysis.phrases:
                children.append(self._paragraph_block(
                    f"• **{phrase.phrase}** — {phrase.meaning} ({phrase.pattern_type})"
                ))
                if phrase.example:
                    children.append(self._paragraph_block(f"  例: {phrase.example}"))

        # Vocabulary
        if analysis.vocabulary:
            children.append(self._heading_block("词汇", level=3))
            for vocab in analysis.vocabulary:
                children.append(self._vocabulary_block(vocab))

        # Examples
        if analysis.examples:
            children.append(self._heading_block("例句", level=3))
            for ex in analysis.examples:
                if ex.chinese:
                    children.append(self._paragraph_block(
                        f"• {ex.swedish}\n  → {ex.chinese}"
                    ))
                else:
                    children.append(self._paragraph_block(f"• {ex.swedish}"))

        # SFI notes
        if analysis.sfi_notes:
            children.append(self._callout_block(
                f"📝 {analysis.sfi_notes}", emoji="🎓"
            ))

        return {
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": title_text}}],
                "children": children,
            },
        }

    def _vocabulary_block(self, vocab: VocabularyEntry) -> dict:  # type: ignore[type-arg]
        """Create a block displaying a vocabulary entry with morphology and dictionary link.

        Args:
            vocab: Vocabulary entry to render.

        Returns:
            Paragraph block with formatted vocabulary and svenska.se link.
        """
        # Build the morphology text
        morph_parts: list[str] = []

        if vocab.verb:
            morph_parts.append(
                f"  动词 (grupp {vocab.verb.group}): "
                f"{vocab.verb.infinitive} / {vocab.verb.present} / "
                f"{vocab.verb.past} / {vocab.verb.supine}"
            )

        if vocab.noun:
            morph_parts.append(
                f"  名词 ({vocab.noun.gender}): "
                f"{vocab.noun.indefinite_singular} / {vocab.noun.definite_singular} / "
                f"{vocab.noun.indefinite_plural} / {vocab.noun.definite_plural}"
            )

        if vocab.adjective:
            morph_parts.append(
                f"  形容词: {vocab.adjective.en_form} / {vocab.adjective.ett_form} / "
                f"{vocab.adjective.plural_definite}"
            )
            if vocab.adjective.comparative:
                morph_parts.append(
                    f"  比较级: {vocab.adjective.comparative} / {vocab.adjective.superlative}"
                )

        # Build rich_text with link on the word
        dict_url = f"https://svenska.se/tre/?sok={vocab.word}"
        rich_text: list[dict] = [  # type: ignore[type-arg]
            {
                "type": "text",
                "text": {"content": vocab.word, "link": {"url": dict_url}},
                "annotations": {"bold": True},
            },
            {
                "type": "text",
                "text": {"content": f" [{vocab.pos}] — {vocab.meaning}"},
            },
        ]

        # Add morphology as separate text
        if morph_parts:
            rich_text.append({
                "type": "text",
                "text": {"content": "\n" + "\n".join(morph_parts)},
            })

        return {
            "type": "paragraph",
            "paragraph": {"rich_text": rich_text},
        }

    def _vocabulary_summary_table(self, lesson: Lesson) -> list[dict]:  # type: ignore[type-arg]
        """Create a summary table of all new words in the lesson with dictionary links.

        Args:
            lesson: The full lesson.

        Returns:
            List of blocks forming a vocabulary list with svenska.se links.
        """
        blocks: list[dict] = []  # type: ignore[type-arg]
        seen_words: set[str] = set()

        for word in lesson.new_words:
            if word.word in seen_words:
                continue
            seen_words.add(word.word)
            dict_url = f"https://svenska.se/tre/?sok={word.word}"
            blocks.append({
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "• "}},
                        {
                            "type": "text",
                            "text": {"content": word.word, "link": {"url": dict_url}},
                            "annotations": {"bold": True},
                        },
                        {
                            "type": "text",
                            "text": {"content": f" [{word.pos}] — {word.meaning}"},
                        },
                    ],
                },
            })

        if not blocks:
            blocks.append(self._paragraph_block("（今天没有新词汇）"))

        return blocks

    # --- Block helper methods ---

    def _heading_block(self, text: str, level: int = 2) -> dict:  # type: ignore[type-arg]
        """Create a heading block."""
        heading_type = f"heading_{level}"
        return {
            "type": heading_type,
            heading_type: {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        }

    def _paragraph_block(self, text: str) -> dict:  # type: ignore[type-arg]
        """Create a paragraph block."""
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        }

    def _callout_block(self, text: str, emoji: str = "💡") -> dict:  # type: ignore[type-arg]
        """Create a callout block with an emoji icon."""
        return {
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": emoji},
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        }
