"""CLI review session — terminal-based flashcard review using spaced repetition."""

import json
import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import UserRecord, WordRecord
from swedish_ai_tutor.services.user_vocabulary_service import UserVocabularyService
from swedish_ai_tutor.services.vocabulary_service import VocabularyService

logger = logging.getLogger(__name__)
console = Console()


def run_review_session(
    settings: Settings, max_words: int = 20, username: str | None = None
) -> None:
    """Run an interactive flashcard review session.

    Presents due words one at a time. The learner sees the Swedish word,
    tries to recall the meaning, then rates their recall quality.

    Args:
        settings: Application settings.
        max_words: Maximum number of words to review this session (default 20).
        username: Account username. Required when multiple accounts exist.
    """
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        users = list(session.scalars(select(UserRecord).order_by(UserRecord.username)))
        if users:
            selected = next((user for user in users if user.username == username), None)
            if username is None and len(users) == 1:
                selected = users[0]
            if selected is None:
                names = ", ".join(user.username for user in users)
                console.print(f"Available accounts: {names}")
                console.print("Use: python -m swedish_ai_tutor review --user <username>")
                return
            _run_account_review_session(
                UserVocabularyService(session, selected.id),
                selected.display_name,
                max_words,
            )
            return

        _run_legacy_review_session(VocabularyService(session), max_words)


def _run_account_review_session(
    service: UserVocabularyService, display_name: str, max_words: int
) -> None:
    """Run terminal review using one learner's isolated schedule."""
    stats = service.get_stats()
    console.print()
    console.print(Panel(
        f"👤 {display_name} | 📚 Total: {stats['total']} | "
        f"🆕 New: {stats['new']} | 📖 Learning: {stats['learning']} | "
        f"✅ Mastered: {stats['mastered']} | 📋 Due: {stats['due']}",
        title="Vocabulary Stats",
    ))
    review_queue = service.get_review_queue(max_words)
    if not review_queue:
        console.print("\n✨ No words due for review! Come back later.\n")
        return

    console.print(f"\n📝 Review session: {len(review_queue)} words\n")
    console.print("Rating: [a]gain(0) [h]ard(2) [g]ood(4) [e]asy(5) [q]uit\n")
    reviewed = 0
    correct = 0
    for index, (word, progress) in enumerate(review_queue, 1):
        console.print(f"── {index}/{len(review_queue)} ──")
        console.print(f"  🇸🇪 [bold]{word.word}[/bold] [{word.pos}]")
        try:
            input("  (press Enter to reveal) ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n\n👋 Session ended.")
            break
        morphology = _format_morphology(word)
        console.print(f"  🇨🇳 {word.meaning}")
        if morphology:
            console.print(f"  📝 {morphology}")
        _print_example(word)
        interval = progress.interval if progress else 0
        console.print(f"  📊 freq={word.frequency} | interval={interval}d")
        rating = _get_rating()
        if rating is None:
            console.print("\n👋 Session ended.")
            break
        service.process_review(word.id, rating)
        reviewed += 1
        if rating >= 3:
            correct += 1
        console.print()

    console.print()
    console.print(Panel(
        f"Reviewed: {reviewed} | Correct: {correct} | Failed: {reviewed - correct}",
        title="Session Complete ✅",
    ))
    console.print()


def _run_legacy_review_session(service: VocabularyService, max_words: int) -> None:
    """Run the original single-learner flow before accounts are configured."""
    stats = service.get_stats()
    console.print()
    console.print(Panel(
        f"📚 Total: {stats['total']} | 🆕 New: {stats['new']} | "
        f"📖 Learning: {stats['learning']} | ✅ Mastered: {stats['mastered']} | "
        f"📋 Due: {stats['due']}",
        title="Vocabulary Stats",
    ))
    due_words = service.get_due_reviews()
    new_words = service.get_new_words()
    review_queue: list[WordRecord] = list(due_words)[:max_words]
    remaining_slots = max_words - len(review_queue)
    if remaining_slots > 0:
        review_queue.extend(
            [word for word in new_words if word not in review_queue][:remaining_slots]
        )
    if not review_queue:
        console.print("\n✨ No words due for review! Come back later.\n")
        return

    console.print(f"\n📝 Review session: {len(review_queue)} words\n")
    console.print("Rating: [a]gain(0) [h]ard(2) [g]ood(4) [e]asy(5) [q]uit\n")
    reviewed = 0
    correct = 0
    for index, word in enumerate(review_queue, 1):
        console.print(f"── {index}/{len(review_queue)} ──")
        console.print(f"  🇸🇪 [bold]{word.word}[/bold] [{word.pos}]")
        try:
            input("  (press Enter to reveal) ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n\n👋 Session ended.")
            break
        morphology = _format_morphology(word)
        console.print(f"  🇨🇳 {word.meaning}")
        if morphology:
            console.print(f"  📝 {morphology}")
        _print_example(word)
        console.print(f"  📊 freq={word.frequency} | interval={word.interval}d")
        rating = _get_rating()
        if rating is None:
            console.print("\n👋 Session ended.")
            break
        service.process_review(word.id, rating)
        reviewed += 1
        if rating >= 3:
            correct += 1
        console.print()

    console.print()
    console.print(Panel(
        f"Reviewed: {reviewed} | Correct: {correct} | Failed: {reviewed - correct}",
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


def _print_example(word: WordRecord) -> None:
    """Print a stored news example after morphology, if available."""
    if not word.examples:
        return
    try:
        example = json.loads(word.examples)
    except json.JSONDecodeError:
        return
    if not isinstance(example, dict):
        return
    swedish = str(example.get("swedish", "")).strip()
    chinese = str(example.get("chinese", "")).strip()
    if swedish:
        console.print(f"  [dim]例句：{swedish}[/dim]")
    if chinese:
        console.print(f"  [dim]中文：{chinese}[/dim]")


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
