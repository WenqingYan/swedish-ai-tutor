"""Dry-run pipeline — tests Notion integration with mock AI data.

Uses realistic fake transcription and analysis data to verify:
1. Notion API connection works
2. Page formatting looks correct
3. All blocks render properly

No OpenAI API calls are made.
"""

import asyncio
import logging
from datetime import UTC, datetime

from swedish_ai_tutor.config import get_settings
from swedish_ai_tutor.exporters.notion_exporter import NotionExporter
from swedish_ai_tutor.models import (
    AdjectiveMorphology,
    Episode,
    ExampleSentence,
    GrammarNote,
    Lesson,
    NounMorphology,
    Phrase,
    SentenceAnalysis,
    Transcript,
    TranscriptSegment,
    VerbMorphology,
    VocabularyEntry,
)

logger = logging.getLogger(__name__)


def _build_mock_lesson() -> Lesson:
    """Build a realistic mock lesson for testing."""
    episode = Episode(
        id=9999999,
        title="Klartext — TEST DRY RUN",
        description="Regeringen vill utreda telefonförsäljning. Ny lag om uppehållstillstånd.",
        publish_date=datetime(2026, 7, 13, 18, 55, tzinfo=UTC),
        audio_url="https://static-cdn.sr.se/test/dry-run.mp3",
        duration_seconds=300,
        url="https://www.sverigesradio.se/avsnitt/9999999",
    )

    transcript = Transcript(
        full_text=(
            "Regeringen vill utreda om telefonförsäljning ska förbjudas i Sverige. "
            "Det är många som blir lurade av telefonförsäljare. "
            "En ny lag gör det lättare att utvisa personer som inte har rätt att vara i Sverige."
        ),
        segments=[
            TranscriptSegment(
                text="Regeringen vill utreda om telefonförsäljning ska förbjudas i Sverige.",
                start=0.0,
                end=5.2,
            ),
            TranscriptSegment(
                text="Det är många som blir lurade av telefonförsäljare.",
                start=5.2,
                end=9.8,
            ),
            TranscriptSegment(
                text="En ny lag gör det lättare att utvisa personer som inte har rätt att vara i Sverige.",
                start=9.8,
                end=16.0,
            ),
        ],
        language="sv",
    )

    analyses = [
        SentenceAnalysis(
            original="Regeringen vill utreda om telefonförsäljning ska förbjudas i Sverige.",
            translation="政府希望调查是否应该在瑞典禁止电话推销。",
            grammar=GrammarNote(
                pattern="Modalverb + infinitiv (vill + utreda)",
                explanation="瑞典语中情态动词(vill, ska, kan等)后面跟动词不定式。这里'vill utreda'表示'想要调查'，'ska förbjudas'表示'应该被禁止'（被动语态）。",
                sfi_relevance="情态动词+不定式是SFI C/D级写作和阅读中的核心结构，几乎每篇新闻都会出现。",
            ),
            phrases=[
                Phrase(
                    phrase="vill utreda",
                    meaning="想要调查",
                    pattern_type="verb_particle",
                    example="Polisen vill utreda brottet.",
                ),
                Phrase(
                    phrase="ska förbjudas",
                    meaning="应该被禁止",
                    pattern_type="collocation",
                    example="Rökning ska förbjudas på restauranger.",
                ),
            ],
            vocabulary=[
                VocabularyEntry(
                    word="utreda",
                    pos="verb",
                    meaning="调查，审查",
                    verb=VerbMorphology(
                        group=2,
                        imperative="utred",
                        infinitive="utreda",
                        present="utreder",
                        past="utredde",
                        supine="utrett",
                    ),
                ),
                VocabularyEntry(
                    word="telefonförsäljning",
                    pos="noun",
                    meaning="电话推销",
                    noun=NounMorphology(
                        gender="en",
                        indefinite_singular="en telefonförsäljning",
                        definite_singular="telefonförsäljningen",
                        indefinite_plural="telefonförsäljningar",
                        definite_plural="telefonförsäljningarna",
                    ),
                ),
                VocabularyEntry(
                    word="förbjuda",
                    pos="verb",
                    meaning="禁止",
                    verb=VerbMorphology(
                        group=4,
                        imperative="förbjud",
                        infinitive="förbjuda",
                        present="förbjuder",
                        past="förbjöd",
                        supine="förbjudit",
                    ),
                ),
            ],
            examples=[
                ExampleSentence(swedish="Kommunen vill utreda om skolan behöver renoveras.", chinese="市政府想要调查学校是否需要翻修。"),
                ExampleSentence(swedish="Plastpåsar ska förbjudas från nästa år.", chinese="塑料袋将从明年起被禁止。"),
            ],
            sfi_notes="被动语态(s-passiv: förbjudas)是SFI D级的重要考点。注意ska + s-passiv的组合。",
        ),
        SentenceAnalysis(
            original="Det är många som blir lurade av telefonförsäljare.",
            translation="有很多人被电话推销员欺骗。",
            grammar=GrammarNote(
                pattern="Det är + adj + som (存在句 + 关系从句)",
                explanation="'Det är många som...'是瑞典语中表达'有很多人...'的固定句式。som引导关系从句。'blir lurade'是被动语态的另一种形式(bli-passiv)。",
                sfi_relevance="det är...som结构在SFI D级阅读和写作中频繁出现。",
            ),
            phrases=[
                Phrase(
                    phrase="det är många som",
                    meaning="有很多人...",
                    pattern_type="fixed_expression",
                    example="Det är många som tycker att det är för dyrt.",
                ),
                Phrase(
                    phrase="blir lurade",
                    meaning="被欺骗",
                    pattern_type="collocation",
                    example="Äldre personer blir ofta lurade på internet.",
                ),
            ],
            vocabulary=[
                VocabularyEntry(
                    word="lura",
                    pos="verb",
                    meaning="欺骗，骗",
                    verb=VerbMorphology(
                        group=1,
                        imperative="lura",
                        infinitive="lura",
                        present="lurar",
                        past="lurade",
                        supine="lurat",
                    ),
                ),
                VocabularyEntry(
                    word="telefonförsäljare",
                    pos="noun",
                    meaning="电话推销员",
                    noun=NounMorphology(
                        gender="en",
                        indefinite_singular="en telefonförsäljare",
                        definite_singular="telefonförsäljaren",
                        indefinite_plural="telefonförsäljare",
                        definite_plural="telefonförsäljarna",
                    ),
                ),
            ],
            examples=[
                ExampleSentence(swedish="Det är få som vet om den nya lagen.", chinese="很少有人知道这项新法律。"),
            ],
            sfi_notes="bli-passiv (blir lurade) 与 s-passiv (luras) 的区别：bli-passiv强调过程/变化。",
        ),
        SentenceAnalysis(
            original="En ny lag gör det lättare att utvisa personer som inte har rätt att vara i Sverige.",
            translation="一项新法律使驱逐没有权利留在瑞典的人变得更容易。",
            grammar=GrammarNote(
                pattern="göra + det + komparativ + att-infinitiv",
                explanation="'göra det lättare att...'是瑞典语中'使...更容易'的固定结构。det是形式宾语，att utvisa是真正的宾语。这是一个复杂但高频的句式。",
                sfi_relevance="这种复杂句式在SFI D级的新闻阅读理解中常见，需要理解句子各部分的逻辑关系。",
            ),
            phrases=[
                Phrase(
                    phrase="göra det lättare att",
                    meaning="使...更容易",
                    pattern_type="fixed_expression",
                    example="Appen gör det lättare att lära sig svenska.",
                ),
                Phrase(
                    phrase="har rätt att",
                    meaning="有权利...",
                    pattern_type="fixed_expression",
                    example="Alla har rätt att söka asyl.",
                ),
            ],
            vocabulary=[
                VocabularyEntry(
                    word="utvisa",
                    pos="verb",
                    meaning="驱逐，遣返",
                    verb=VerbMorphology(
                        group=1,
                        imperative="utvisa",
                        infinitive="utvisa",
                        present="utvisar",
                        past="utvisade",
                        supine="utvisat",
                    ),
                ),
                VocabularyEntry(
                    word="lätt",
                    pos="adj",
                    meaning="容易的；轻的",
                    adjective=AdjectiveMorphology(
                        en_form="lätt",
                        ett_form="lätt",
                        plural_definite="lätta",
                        comparative="lättare",
                        superlative="lättast",
                    ),
                ),
                VocabularyEntry(
                    word="lag",
                    pos="noun",
                    meaning="法律",
                    noun=NounMorphology(
                        gender="en",
                        indefinite_singular="en lag",
                        definite_singular="lagen",
                        indefinite_plural="lagar",
                        definite_plural="lagarna",
                    ),
                ),
            ],
            examples=[
                ExampleSentence(swedish="Den nya reformen gör det svårare att fuska med bidrag.", chinese="新改革使骗取补贴变得更困难。"),
            ],
            sfi_notes="注意关系从句'som inte har rätt att vara i Sverige'修饰'personer'。嵌套从句是D级的难点。",
        ),
    ]

    from swedish_ai_tutor.models.lesson import NewsStory

    return Lesson(
        episode=episode,
        transcript=transcript,
        stories=[
            NewsStory(
                headline="Regeringen vill utreda telefonförsäljning",
                analyses=[analyses[0], analyses[1]],
            ),
            NewsStory(
                headline="Ny lag om utvisning",
                analyses=[analyses[2]],
            ),
        ],
    )


async def run_dry_run() -> None:
    """Run the pipeline with mock data to test Notion integration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("=== DRY RUN — Testing Notion Integration ===")
    logger.info("No OpenAI API calls will be made.")

    # Load settings (only needs NOTION keys)
    try:
        settings = get_settings()
    except Exception as e:
        logger.error("Configuration error: %s", e)
        logger.error("Make sure .env has NOTION_API_KEY and NOTION_PARENT_PAGE_ID set.")
        print(f"❌ Config error: {e}")
        return

    # Build mock lesson
    logger.info("Building mock lesson with 3 sample sentences...")
    lesson = _build_mock_lesson()
    logger.info(
        "Mock lesson: %d sentences, %d words, %d phrases",
        lesson.sentence_count,
        len(lesson.new_words),
        len(lesson.all_phrases),
    )

    # Export to Notion
    logger.info("Creating Notion page...")
    try:
        exporter = NotionExporter(
            api_key=settings.notion_api_key,
            parent_page_id=settings.notion_parent_page_id,
        )
        url = await exporter.create_lesson_page(lesson)
        print("✅ Notion page created successfully!")
        print(f"📖 URL: {url}")
        print()
        print("Check the page in Notion to verify the format.")
        print("If it looks good, run the real pipeline with:")
        print("  python -m swedish_ai_tutor run")
    except Exception as e:
        logger.error("Notion export failed: %s", e)
        print(f"❌ Notion export failed: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check NOTION_API_KEY is correct")
        print("2. Check NOTION_PARENT_PAGE_ID is correct (32 hex chars from URL)")
        print("3. Make sure the page is shared with your integration")


def main() -> None:
    """Entry point for dry-run."""
    asyncio.run(run_dry_run())


if __name__ == "__main__":
    main()
