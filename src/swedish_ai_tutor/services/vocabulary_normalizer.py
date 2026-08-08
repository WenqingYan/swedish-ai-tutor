"""Canonicalization helpers for vocabulary identity and deduplication."""

from swedish_ai_tutor.models.lesson import VocabularyEntry

_POS_ALIASES = {
    "adjective": "adj",
    "adverb": "adv",
    "conj": "conjunction",
    "prep": "preposition",
    "pron": "pronoun",
}


def normalize_pos(pos: str) -> str:
    """Return one stable database label for common POS aliases."""
    normalized = pos.strip().lower()
    return _POS_ALIASES.get(normalized, normalized or "unknown")


def canonicalize_entry(entry: VocabularyEntry) -> VocabularyEntry:
    """Use morphology to convert an inflected vocabulary item to dictionary form."""
    word = entry.word.strip()
    pos = normalize_pos(entry.pos)
    if entry.verb and entry.verb.infinitive.strip():
        word = entry.verb.infinitive.strip()
    elif entry.noun and entry.noun.indefinite_singular.strip():
        word = _strip_noun_article(entry.noun.indefinite_singular)
    elif entry.adjective and entry.adjective.en_form.strip():
        word = entry.adjective.en_form.strip()
    return entry.model_copy(update={"word": word.lower(), "pos": pos})


def canonical_word_from_morphology(
    word: str, pos: str, morphology: dict[str, object] | None
) -> tuple[str, str]:
    """Canonicalize an existing database row from its stored morphology JSON."""
    canonical = word.strip().lower()
    normalized_pos = normalize_pos(pos)
    if morphology:
        morphology_type = str(morphology.get("type", ""))
        if morphology_type == "verb":
            canonical = str(morphology.get("infinitive", canonical)).strip().lower()
        elif morphology_type == "noun":
            singular = str(morphology.get("indefinite_singular", canonical))
            canonical = _strip_noun_article(singular).lower()
        elif morphology_type == "adjective":
            canonical = str(morphology.get("en_form", canonical)).strip().lower()
    return canonical or word.strip().lower(), normalized_pos


def _strip_noun_article(value: str) -> str:
    """Remove an optional indefinite article from a noun dictionary form."""
    value = value.strip()
    lowered = value.lower()
    for article in ("en ", "ett "):
        if lowered.startswith(article):
            return value[len(article) :].strip()
    return value
