"""CLI entry point for the Swedish AI Tutor.

Usage:
    python -m swedish_ai_tutor run              Process all news stories
    python -m swedish_ai_tutor run --news 2     Randomly pick 2 stories
    python -m swedish_ai_tutor dry-run          Test Notion with mock data
    python -m swedish_ai_tutor review           Flashcard review session
    python -m swedish_ai_tutor vocab            Show vocabulary statistics
    python -m swedish_ai_tutor add-word <word>  Manually add a word
"""

import asyncio
import sys

from swedish_ai_tutor.config import get_settings
from swedish_ai_tutor.services.pipeline import run_pipeline


def main() -> None:
    """Main entry point for the CLI."""
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _print_usage()
        return

    command = sys.argv[1]

    if command == "run":
        _run_pipeline()
    elif command == "dry-run":
        _run_dry_run()
    elif command == "review":
        _run_review()
    elif command == "vocab":
        _show_vocab()
    elif command == "web":
        _run_web()
    elif command == "rebuild-vocab":
        _rebuild_vocab()
    elif command == "rebuild-phrases":
        _rebuild_phrases()
    elif command == "dedupe-vocab":
        _dedupe_vocab()
    elif command == "add-word":
        _add_word()
    else:
        print(f"Unknown command: {command}")
        _print_usage()
        sys.exit(1)


def _parse_news_flag() -> int | None:
    """Parse --news N flag from sys.argv."""
    for i, arg in enumerate(sys.argv):
        if arg == "--news" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                print(f"Error: --news requires a number, got '{sys.argv[i + 1]}'")
                sys.exit(1)
    return None


def _run_pipeline() -> None:
    """Execute the daily lesson pipeline."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        print("Make sure .env file exists with required API keys.")
        print("See .env.example for required variables.")
        sys.exit(1)

    # Override max_news from CLI flag if provided
    news_count = _parse_news_flag()
    if news_count is not None:
        settings.max_news = news_count

    if settings.max_news > 0:
        print(f"📰 Will randomly pick {settings.max_news} news story/stories from today's episode")
    else:
        print("📰 Processing all news stories from today's episode")

    result = asyncio.run(run_pipeline(settings))

    if result.success:
        print(f"✅ {result.message}")
        if result.notion_url:
            print(f"📖 Notion page: {result.notion_url}")
    else:
        print(f"❌ {result.message}")
        sys.exit(1)


def _run_dry_run() -> None:
    """Run dry-run with mock data to test Notion integration."""
    from swedish_ai_tutor.dry_run import main as dry_run_main

    dry_run_main()


def _run_review() -> None:
    """Start a flashcard review session."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Parse --count N flag (default 20)
    max_words = 20
    username = None
    for i, arg in enumerate(sys.argv):
        if arg in ("--count", "-n") and i + 1 < len(sys.argv):
            try:
                max_words = int(sys.argv[i + 1])
            except ValueError:
                print(f"Error: --count requires a number, got '{sys.argv[i + 1]}'")
                sys.exit(1)
        if arg == "--user" and i + 1 < len(sys.argv):
            username = sys.argv[i + 1].strip().lower()

    from swedish_ai_tutor.review.session import run_review_session

    run_review_session(settings, max_words=max_words, username=username)


def _show_vocab() -> None:
    """Show vocabulary database statistics."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    from swedish_ai_tutor.review.session import show_vocab_stats

    show_vocab_stats(settings)


def _run_web() -> None:
    """Start the private mobile vocabulary review web app."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    host = "127.0.0.1"
    port = 8000
    for i, arg in enumerate(sys.argv):
        if arg == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
        if arg == "--port" and i + 1 < len(sys.argv):
            try:
                port = int(sys.argv[i + 1])
            except ValueError:
                print(f"Error: --port requires a number, got '{sys.argv[i + 1]}'")
                sys.exit(1)

    import uvicorn

    from swedish_ai_tutor.web.app import create_app

    print(f"Starting vocabulary review at http://{host}:{port}")
    if host != "127.0.0.1":
        print("Warning: this exposes the app to other devices on the network.")
    uvicorn.run(create_app(settings), host=host, port=port)


def _rebuild_vocab() -> None:
    """Repopulate vocabulary from saved local lessons without API calls."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    from swedish_ai_tutor.rebuild_vocabulary import rebuild_vocabulary

    try:
        result = rebuild_vocabulary(settings)
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"Rebuild error: {e}")
        sys.exit(1)

    print("✅ Vocabulary rebuilt locally (no API calls)")
    print(
        f"   {result['lesson_files']} lessons, {result['lesson_words']} lesson words, "
        f"{result['created']} created, {result['updated']} updated, "
        f"{result['preserved']} extra/manual preserved"
    )


def _add_word() -> None:
    """Add a word, enriching it through the configured API by default."""
    if len(sys.argv) < 3:
        print("Usage: python -m swedish_ai_tutor add-word <word> [pos] [meaning] [--no-api]")
        print()
        print("Examples:")
        print('  python -m swedish_ai_tutor add-word "utreda"')
        print('  python -m swedish_ai_tutor add-word "utreda" verb "调查"')
        sys.exit(1)

    word = sys.argv[2]
    arguments = [arg for arg in sys.argv[3:] if arg != "--no-api"]
    pos = arguments[0] if arguments else "unknown"
    meaning = arguments[1] if len(arguments) > 1 else ""
    use_api = "--no-api" not in sys.argv[3:]

    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
    from swedish_ai_tutor.services.vocabulary_service import VocabularyService

    morphology = None
    example = None
    if use_api:
        from swedish_ai_tutor.services.word_enricher import WordEnricher, WordEnrichmentError

        print(f"🔎 Looking up {word} and generating a review example…")
        try:
            enriched = asyncio.run(
                WordEnricher(settings.openai_api_key, settings.openai_model).enrich(
                    word, pos, meaning
                )
            )
        except WordEnrichmentError as exc:
            print(f"❌ API enrichment failed: {exc}")
            print("   Nothing was added. Retry, or use --no-api for a manual entry.")
            sys.exit(1)
        word = enriched.entry.word
        pos = enriched.entry.pos
        meaning = enriched.entry.meaning
        morphology = VocabularyService._build_morphology_dict(enriched.entry)  # noqa: SLF001
        example = enriched.example.model_dump()

    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        service = VocabularyService(session)
        record = service.add_manual_word(
            word=word,
            pos=pos,
            meaning=meaning,
            morphology=morphology,
            example=example,
        )
        print(f"✅ Added: {record.word} [{record.pos}] — {record.meaning}")
        if morphology:
            print("   ✓ Morphology completed")
        if example:
            print(f"   例句: {example['swedish']}")
            print(f"         {example['chinese']}")
        print(f"   First review scheduled: {record.next_review}")


def _dedupe_vocab() -> None:
    """Normalize dictionary forms and safely merge existing duplicate cards."""
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    from swedish_ai_tutor.dedupe_vocabulary import dedupe_vocabulary

    try:
        result = dedupe_vocabulary(settings.db_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Deduplication error: {exc}")
        sys.exit(1)
    print(f"✅ Vocabulary normalized: {result.merged} duplicates merged")
    print(f"   {result.renamed} inflected entries renamed to dictionary form")
    print(f"   Backup: {result.backup_path}")


def _rebuild_phrases() -> None:
    """Backfill phrases from saved lesson JSON without API calls."""
    try:
        settings = get_settings()
    except Exception as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)
    from swedish_ai_tutor.rebuild_phrases import rebuild_phrases

    try:
        result = rebuild_phrases(settings)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Phrase rebuild error: {exc}")
        sys.exit(1)
    print("✅ Phrase catalog rebuilt locally (no API calls)")
    print(
        f"   {result['lesson_files']} lessons, {result['phrases']} phrases, "
        f"{result['created']} created, {result['updated']} updated, "
        f"{result['removed']} invalid removed"
    )
    if result["backup"]:
        print(f"   Backup: {result['backup']}")


def _print_usage() -> None:
    """Print usage information."""
    print("Swedish AI Tutor — Daily Lesson Pipeline + Vocabulary Review")
    print()
    print("Commands:")
    print("  run              Run the daily lesson pipeline")
    print("  run --news N     Only analyze N randomly chosen news stories")
    print("  dry-run          Test Notion integration with mock data")
    print("  review           Start a flashcard review session (default: 20 words)")
    print("  review -n 10     Review only 10 words")
    print("  review --user U  Review using account U's memory curve")
    print("  vocab            Show vocabulary statistics")
    print("  web              Start the private mobile review web app")
    print("  rebuild-vocab    Repopulate vocabulary from local lesson JSON (no API calls)")
    print("  rebuild-phrases  Repopulate phrases from local lesson JSON (no API calls)")
    print("  dedupe-vocab     Merge inflected duplicates while preserving review progress")
    print("  add-word <word>  Add a word; API fills meaning, forms, and example")
    print()
    print("Examples:")
    print("  python -m swedish_ai_tutor run --news 2")
    print("  python -m swedish_ai_tutor review")
    print("  python -m swedish_ai_tutor web")
    print('  python -m swedish_ai_tutor add-word "utreda" verb "调查"')
    print()
    print("Setup:")
    print("  Copy .env.example to .env and fill in your API keys.")


if __name__ == "__main__":
    main()
