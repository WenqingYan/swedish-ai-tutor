"""CLI review session — terminal-based flashcard review using spaced repetition."""

import json
import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import WordRecord
from swedish_ai_tutor.services.vocabulary_service import VocabularyService

logger = logging.getLogger(__name__)
console = Console()


def run_review_session(settings: Settings, max_words: int = 20) -> None:
    """Run an interactive flashcard review session.

    Presents due words one at a time. The learner sees the Swedish word,
    tries to recall the meaning, then rates their recall quality.

    Args:
        settings: Application settings.
        max_words: Maximum number of words to review this session (default 20).
    """
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        service = VocabularyService(session)
        stats = service.get_stats()

        # Show stats
        console.print()
        console.print(Panel(
            f"📚 Total: {stats['total']} | "
            f"🆕 New: {stats['new']} | "
            f"📖 Learning: {stats['learning']} | "
            f"✅ Mastered: {stats['mastered']} | "
            f"📋 Due: {stats['due']}",
            title="Vocabulary Stats",
        ))

        # Get due words + new words
        due_words = service.get_due_reviews()
        new_words = service.get_new_words()

        # Combine: due first, then fill remaining slots with new words
        review_queue: list[WordRecord] = list(due_words)[:max_words]
        remaining_slots = max_words - len(review_queue)
        if remaining_slots > 0:
            new_to_add = [w for w in new_words if w not in review_queue][:remaining_slots]
            review_queue.extend(new_to_add)

        if not review_queue:
            console.print("\n✨ No words due for review! Come back later.\n")
            return

        console.print(f"\n📝 Review session: {len(review_queue)} words\n")
        console.print("Rating: [a]gain(0) [h]ard(2) [g]ood(4) [e]asy(5) [q]uit\n")

        reviewed = 0
        correct = 0

        for i, word in enumerate(review_queue, 1):
            # Show the flashcard front (Swedish word)
            console.print(f"── {i}/{len(review_queue)} ──")
            console.print(f"  🇸🇪 [bold]{word.word}[/bold] [{word.pos}]")

            # Wait for user to press Enter to reveal
            try:
                input("  (press Enter to reveal) ")
            except (KeyboardInterrupt, EOFError):
                console.print("\n\n👋 Session ended.")
                break

            # Show the answer
            morphology = _format_morphology(word)
            console.print(f"  🇨🇳 {word.meaning}")
            if morphology:
                console.print(f"  📝 {morphology}")
            console.print(f"  📊 freq={word.frequency} | interval={word.interval}d")

            # Get rating
            rating = _get_rating()
            if rating is None:
                console.print("\n👋 Session ended.")
                break

            # Process the review
            service.process_review(word.id, rating)
            reviewed += 1
            if rating >= 3:
                correct += 1

            console.print()

        # Session summary
        console.print()
        console.print(Panel(
            f"Reviewed: {reviewed} | "
            f"Correct: {correct} | "
            f"Failed: {reviewed - correct}",
            title="Session Complete ✅",
        ))
        console.print()


def _get_rating() -> int | None:
    """Prompt user for a quality rating.

    Returns:
        Rating 0-5, or None to quit.
    """
    rating_map = {"a": 0, "h": 2, "g": 4, "e": 5, "q": None}

    while True:
        try:
            choice = input("  Rate [a/h/g/e/q]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return None

        if choice in rating_map:
            return rating_map[choice]

        # Also accept raw numbers
        try:
            num = int(choice)
            if 0 <= num <= 5:
                return num
        except ValueError:
            pass

        console.print("  Invalid. Use: a(again) h(hard) g(good) e(easy) q(quit)")


def _format_morphology(word: WordRecord) -> str:
    """Format morphology for display.

    Args:
        word: Word record with JSON morphology.

    Returns:
        Formatted string, or empty if no morphology.
    """
    if not word.morphology:
        return f"Ordklass: {word.pos}\n  Böjningsformer: —"

    try:
        data = json.loads(word.morphology)
    except json.JSONDecodeError:
        return f"Ordklass: {word.pos}\n  Böjningsformer: —"

    morph_type = data.get("type", "")

    def value(field: str) -> str:
        """Return a printable morphology value."""
        raw = data.get(field)
        return str(raw) if raw not in (None, "") else "—"

    if morph_type == "verb":
        return (
            f"Verb Group: grupp {value('group')}\n"
            f"  Imperativ:  {value('imperative')}\n"
            f"  Infinitiv:  {value('infinitive')}\n"
            f"  Presens:    {value('present')}\n"
            f"  Preteritum: {value('past')}\n"
            f"  Supinum:    {value('supine')}"
        )
    if morph_type == "noun":
        return (
            f"Noun Group: {value('gender')}-ord\n"
            f"  Obestämd singular: {value('indefinite_singular')}\n"
            f"  Bestämd singular:  {value('definite_singular')}\n"
            f"  Obestämd plural:   {value('indefinite_plural')}\n"
            f"  Bestämd plural:    {value('definite_plural')}"
        )
    if morph_type == "adjective":
        return (
            "Adjective Group\n"
            f"  en-form:         {value('en_form')}\n"
            f"  ett-form:        {value('ett_form')}\n"
            f"  Plural/bestämd:  {value('plural_definite')}\n"
            f"  Komparativ:      {value('comparative')}\n"
            f"  Superlativ:      {value('superlative')}"
        )
    return f"Ordklass: {word.pos}\n  Böjningsformer: —"


def show_vocab_stats(settings: Settings) -> None:
    """Display vocabulary statistics without starting a review.

    Args:
        settings: Application settings.
    """
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        service = VocabularyService(session)
        stats = service.get_stats()

        console.print()
        table = Table(title="📚 Vocabulary Database")
        table.add_column("Category", style="bold")
        table.add_column("Count", justify="right")
        table.add_row("Total words", str(stats["total"]))
        table.add_row("New (unreviewed)", str(stats["new"]))
        table.add_row("Learning", str(stats["learning"]))
        table.add_row("Mastered", str(stats["mastered"]))
        table.add_row("Due for review", str(stats["due"]))
        console.print(table)
        console.print()
