"""Pipeline orchestrator — wires all services into the daily lesson flow.

This is the top-level entry point that coordinates:
SR fetch → audio download → transcription → analysis → Notion export.
"""

import logging
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.repositories.article_repo import ArticleRepository
from swedish_ai_tutor.exporters.notion_exporter import NotionExporter
from swedish_ai_tutor.models.lesson import Lesson, NewsStory
from swedish_ai_tutor.services.sentence_analyzer import SentenceAnalyzer
from swedish_ai_tutor.services.sr_fetcher import SRFetcher
from swedish_ai_tutor.services.transcriber import WhisperAPITranscriber

logger = logging.getLogger(__name__)


class PipelineResult:
    """Result of a pipeline execution."""

    def __init__(
        self,
        success: bool,
        message: str,
        lesson: Lesson | None = None,
        notion_url: str | None = None,
    ) -> None:
        """Initialize pipeline result.

        Args:
            success: Whether the pipeline completed successfully.
            message: Human-readable status message.
            lesson: The generated lesson (if successful).
            notion_url: URL of the created Notion page (if exported).
        """
        self.success = success
        self.message = message
        self.lesson = lesson
        self.notion_url = notion_url


async def run_pipeline(settings: Settings) -> PipelineResult:
    """Execute the full daily lesson pipeline.

    Steps:
    1. Fetch yesterday's episode from SR API
    2. Check if already processed (dedup)
    3. Download audio
    4. Transcribe with Whisper
    5. Analyze sentences with LLM
    6. Create Notion page
    7. Record in database

    Args:
        settings: Application settings.

    Returns:
        PipelineResult with status and optional lesson/URL.
    """
    settings.ensure_directories()

    # Setup logging
    _configure_logging(settings)

    logger.info("=== Swedish AI Tutor — Daily Pipeline ===")
    logger.info("Starting pipeline at %s", datetime.now(UTC).isoformat())

    # Initialize database
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)

    # Step 1: Fetch episode
    logger.info("Step 1: Fetching episode from SR API...")
    fetcher = SRFetcher(
        program_id=settings.sr_program_id,
        api_base=settings.sr_api_base,
    )

    try:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        episode = await fetcher.get_latest_episode(target_date=yesterday)
        if not episode:
            # Try fetching the most recent episode (handles weekends)
            episode = await fetcher.get_latest_episode()
    finally:
        await fetcher.close()

    if not episode:
        return PipelineResult(
            success=True,
            message="No new episode available.",
        )

    logger.info("Found episode: %s (id=%d)", episode.title, episode.id)

    # Step 2: Check deduplication
    with session_factory() as session:
        repo = ArticleRepository(session)
        if repo.exists(episode.id):
            return PipelineResult(
                success=True,
                message=f"Episode {episode.id} already processed. Skipping.",
            )

    # Step 3: Download audio
    logger.info("Step 3: Downloading audio...")
    fetcher2 = SRFetcher(
        program_id=settings.sr_program_id,
        api_base=settings.sr_api_base,
    )
    try:
        audio_path = await fetcher2.download_audio(episode, settings.audio_dir)
    finally:
        await fetcher2.close()
    logger.info("Audio saved: %s", audio_path)

    # Step 4: Transcribe
    logger.info("Step 4: Transcribing audio...")
    transcriber = WhisperAPITranscriber(
        api_key=settings.openai_api_key,
        model=settings.whisper_model,
    )
    transcript = await transcriber.transcribe(audio_path)
    logger.info(
        "Transcription complete: %d characters, %d sentences",
        len(transcript.full_text),
        len(transcript.sentences),
    )

    # Step 5: Segment into news stories and select
    logger.info("Step 5: Segmenting transcript into news stories...")

    # Radio Sweden på lätt svenska uses "/" to separate stories in description
    story_headlines = [
        s.strip() for s in episode.description.split("/")
        if s.strip() and len(s.strip()) > 5
    ]
    num_stories = len(story_headlines) if story_headlines else 4
    logger.info(
        "Episode contains ~%d news stories: %s",
        num_stories, " / ".join(story_headlines[:4]),
    )

    # Segment the transcript sentences into groups (one per news story)
    all_sentences = transcript.sentences
    story_groups = _segment_stories(all_sentences, story_headlines)

    # Select stories based on max_news setting
    if settings.max_news > 0 and len(story_groups) > settings.max_news:
        selected_indices = sorted(random.sample(range(len(story_groups)), settings.max_news))
        selected_stories = [story_groups[i] for i in selected_indices]
        logger.info(
            "Randomly selected %d/%d news stories for today's lesson",
            settings.max_news, len(story_groups),
        )
    else:
        selected_stories = story_groups

    # Build headline list matching selected stories
    selected_headlines: list[str] = []
    if settings.max_news > 0 and len(story_groups) > settings.max_news:
        selected_headlines = [story_headlines[i] for i in selected_indices]
    else:
        selected_headlines = story_headlines[:len(selected_stories)]

    # Pad headlines if we have fewer than stories
    while len(selected_headlines) < len(selected_stories):
        selected_headlines.append(f"Nyhet {len(selected_headlines) + 1}")

    total_sentences = sum(len(s) for s in selected_stories)
    logger.info(
        "Analyzing %d sentences from %d stories",
        total_sentences, len(selected_stories),
    )

    # Step 6: Analyze sentences per story
    logger.info("Step 6: Analyzing sentences with LLM...")
    analyzer = SentenceAnalyzer(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )

    news_stories: list[NewsStory] = []
    for idx, (headline, story_sentences) in enumerate(
        zip(selected_headlines, selected_stories, strict=False), 1
    ):
        logger.info(
            "Story %d/%d: %s (%d sentences)",
            idx, len(selected_stories), headline, len(story_sentences),
        )
        story_analyses = await analyzer.analyze_sentences(story_sentences)
        news_stories.append(NewsStory(headline=headline, analyses=story_analyses))

    logger.info(
        "Analysis complete: %d stories, %d total sentences",
        len(news_stories), sum(len(s.analyses) for s in news_stories),
    )

    # Build lesson
    lesson = Lesson(
        episode=episode,
        transcript=transcript,
        stories=news_stories,
    )

    # Save lesson JSON locally (fallback/debug)
    _save_lesson_json(lesson, settings.lessons_dir)

    # Step 7: Persist vocabulary to database
    logger.info("Step 7: Saving vocabulary to database...")
    from swedish_ai_tutor.services.vocabulary_service import VocabularyService

    with session_factory() as session:
        vocab_service = VocabularyService(session)
        vocab_stats = vocab_service.upsert_from_lesson(lesson)
    logger.info(
        "Vocabulary: %d new words, %d updated",
        vocab_stats["new_words"], vocab_stats["updated_words"],
    )

    # Step 8: Export to Notion
    logger.info("Step 8: Creating Notion page...")
    notion_url: str | None = None
    try:
        exporter = NotionExporter(
            api_key=settings.notion_api_key,
            parent_page_id=settings.notion_parent_page_id,
        )
        notion_url = await exporter.create_lesson_page(lesson)
        logger.info("Notion page created: %s", notion_url)
    except Exception as e:
        logger.error("Notion export failed: %s. Lesson saved locally.", e)

    # Step 9: Record in database
    with session_factory() as session:
        repo = ArticleRepository(session)
        repo.create(episode, notion_page_id=notion_url)

    logger.info("=== Pipeline complete! ===")
    return PipelineResult(
        success=True,
        message=f"Lesson created for {episode.date_str}",
        lesson=lesson,
        notion_url=notion_url,
    )


def _save_lesson_json(lesson: Lesson, output_dir: Path) -> None:
    """Save lesson as JSON for debugging and fallback.

    Args:
        lesson: The lesson to save.
        output_dir: Directory to save into.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"lesson_{lesson.episode.date_str}_{lesson.episode.id}.json"
    output_path = output_dir / filename
    output_path.write_text(lesson.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Lesson JSON saved: %s", output_path)


def _configure_logging(settings: Settings) -> None:
    """Configure logging based on settings.

    Args:
        settings: Application settings with log_level.
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _segment_stories(
    sentences: list[str],
    headlines: list[str],
) -> list[list[str]]:
    """Segment transcript sentences into story groups using headline matching.

    Uses keywords from each headline to find the sentence where a new story
    begins. Falls back to equal-sized chunks if matching fails.

    Args:
        sentences: All transcript sentences.
        headlines: Story headlines parsed from episode description.

    Returns:
        List of sentence groups, one per story.
    """
    num_stories = len(headlines)
    if num_stories <= 1 or len(sentences) <= num_stories:
        return [sentences]

    # Extract significant keywords from each headline (skip short/common words)
    stop_words = {
        "i", "på", "av", "för", "med", "och", "att", "som", "är", "har",
        "kan", "ska", "vill", "det", "den", "de", "ett", "en", "inte",
        "nu", "nya", "till", "från", "om", "mer", "sig", "bli", "alla",
        "mot", "sin", "sitt", "sina", "får", "efter", "under", "över",
        "utan", "också", "bara", "redan", "just", "även",
    }

    def _get_keywords(headline: str) -> list[str]:
        """Extract significant words from a headline."""
        words = headline.lower().split()
        return [w for w in words if len(w) > 3 and w not in stop_words]

    # Find the start index for each story (skip story 0 — it starts at index 0/1)
    boundary_indices: list[int] = [0]  # First story always starts at beginning

    # Skip the intro sentence (usually "Det här är Radio Sweden...")
    # Start searching for story 1's content from index 1
    if sentences and "radio sweden" in sentences[0].lower():
        boundary_indices[0] = 1

    for story_idx in range(1, num_stories):
        keywords = _get_keywords(headlines[story_idx])
        if not keywords:
            boundary_indices.append(-1)
            continue

        # Search for a sentence containing headline keywords
        prev_boundary = boundary_indices[-1] if boundary_indices[-1] >= 0 else 0
        min_search = prev_boundary + 3  # At least 3 sentences per story
        max_search = min(len(sentences), prev_boundary + len(sentences) // 2)

        best_idx = -1
        best_score = 0

        for sent_idx in range(min_search, max_search):
            sent_lower = sentences[sent_idx].lower()
            score = sum(1 for kw in keywords if kw in sent_lower)
            if score > best_score:
                best_score = score
                best_idx = sent_idx

        # Require at least 1 keyword match
        min_score = 1
        if best_score >= min_score and best_idx >= 0:
            # Look backwards from the keyword match to find the actual
            # topic start. News stories often begin by introducing a person,
            # place, or situation before using the headline keywords.
            story_start = _find_topic_start(
                sentences, best_idx, min_search, keywords,
            )
            boundary_indices.append(story_start)
        else:
            boundary_indices.append(-1)

    # Check if we successfully found boundaries
    found_count = sum(1 for b in boundary_indices if b >= 0)

    if found_count < num_stories:
        # Fallback: equal-sized chunks for any missing boundaries
        logger.warning(
            "Could only match %d/%d story boundaries by headline keywords. "
            "Using equal-split fallback for unmatched stories.",
            found_count, num_stories,
        )
        # Fill in missing boundaries with equal spacing
        chunk_size = len(sentences) // num_stories
        for i in range(len(boundary_indices)):
            if boundary_indices[i] < 0:
                boundary_indices[i] = i * chunk_size

    # Ensure boundaries are strictly increasing
    for i in range(1, len(boundary_indices)):
        if boundary_indices[i] <= boundary_indices[i - 1]:
            boundary_indices[i] = boundary_indices[i - 1] + 3

    # Build story groups from boundaries
    story_groups: list[list[str]] = []
    for i in range(num_stories):
        start = boundary_indices[i]
        end = boundary_indices[i + 1] if i + 1 < len(boundary_indices) else len(sentences)
        # Strip outro sentences from the last story
        if i == num_stories - 1:
            # Remove trailing "Du kan läsa...", "Tack för att du lyssnar...", etc.
            while end > start and _is_outro_sentence(sentences[end - 1]):
                end -= 1
        story_groups.append(sentences[start:end])

    logger.info(
        "Story segmentation: %s",
        " | ".join(f"{headlines[i][:30]}…: {len(g)} sent" for i, g in enumerate(story_groups)),
    )

    return story_groups


def _is_outro_sentence(sentence: str) -> bool:
    """Check if a sentence is part of the program outro.

    Args:
        sentence: The sentence to check.

    Returns:
        True if the sentence is part of outro/sign-off.
    """
    lower = sentence.lower()
    outro_markers = [
        "tack för att du lyssnar",
        "du kan läsa texten",
        "ladda ner appen",
        "lyssna på radio sweden",
        "gu.se",
        "sr.se",
        "vår hemsida",
        "vår app",
        "valkompassen",
    ]
    return any(marker in lower for marker in outro_markers)


def _find_topic_start(
    sentences: list[str],
    keyword_match_idx: int,
    earliest_allowed: int,
    keywords: list[str],
) -> int:
    """Find the actual start of a news story by looking back from keyword match.

    News stories typically begin with a general introductory sentence before
    mentioning specific headline keywords. This function walks backwards
    from the first keyword match to find where the topic actually starts.

    Args:
        sentences: All transcript sentences.
        keyword_match_idx: Index where headline keywords were first matched.
        earliest_allowed: Don't look back further than this index.
        keywords: Significant keywords from the headline.

    Returns:
        Best estimate of where the story actually begins.
    """
    # Look backwards from keyword match to earliest allowed position
    search_start = earliest_allowed

    # Build search terms: full keywords + roots + compound parts
    search_terms: set[str] = set()
    for kw in keywords:
        search_terms.add(kw)
        # Add root (first 5 chars) for partial matching
        if len(kw) >= 5:
            search_terms.add(kw[:5])
        # For compound words (>8 chars), also try splitting at common points
        # e.g., "hundhotell" → "hund", "hotell"
        if len(kw) > 8:
            for split_pos in range(4, len(kw) - 3):
                part1 = kw[:split_pos]
                part2 = kw[split_pos:]
                if len(part1) >= 4:
                    search_terms.add(part1)
                if len(part2) >= 4:
                    search_terms.add(part2)

    # Find the earliest sentence that contains any search term
    earliest_keyword_idx = keyword_match_idx

    for idx in range(search_start, keyword_match_idx):
        sent_lower = sentences[idx].lower()
        if any(term in sent_lower for term in search_terms):
            earliest_keyword_idx = idx
            break

    return earliest_keyword_idx
