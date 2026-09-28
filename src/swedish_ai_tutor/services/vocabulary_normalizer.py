"""Canonicalization helpers for vocabulary identity and deduplication."""

from typing import Any

from swedish_ai_tutor.models.lesson import VocabularyEntry

_POS_ALIASES = {
    "adjective": "adj",
    "adverb": "adv",
    "conj": "conjunction",
    "prep": "preposition",
    "pron": "pronoun",
}

def _adjective_forms(
    en: str, ett: str, plural: str, comparative: str, superlative: str
) -> dict[str, str]:
    """Build one complete adjective morphology mapping."""
    return {
        "type": "adjective",
        "en_form": en,
        "ett_form": ett,
        "plural_definite": plural,
        "comparative": comparative,
        "superlative": superlative,
    }


_IRREGULAR_ADJECTIVES: dict[str, dict[str, str]] = {
    "bra": _adjective_forms("bra", "bra", "bra", "bättre", "bäst"),
    "dålig": _adjective_forms("dålig", "dåligt", "dåliga", "sämre", "sämst"),
    "låg": _adjective_forms("låg", "lågt", "låga", "lägre", "lägst"),
    "stor": _adjective_forms("stor", "stort", "stora", "större", "störst"),
    "ung": _adjective_forms("ung", "ungt", "unga", "yngre", "yngst"),
    "gammal": _adjective_forms("gammal", "gammalt", "gamla", "äldre", "äldst"),
    "liten": _adjective_forms("liten", "litet", "små", "mindre", "minst"),
    "få": _adjective_forms("få", "få", "få", "färre", "färst"),
    "sen": _adjective_forms("sen", "sent", "sena", "senare", "senast"),
}

_IRREGULAR_ADJECTIVE_LOOKUP = {
    form.lower(): base
    for base, forms in _IRREGULAR_ADJECTIVES.items()
    for form in forms.values()
    if form != "—"
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
        elif morphology_type == "adjective" or normalized_pos == "adj":
            canonical = canonical_adjective(word, morphology)
    return canonical or word.strip().lower(), normalized_pos


def canonical_adjective(word: str, morphology: dict[str, object]) -> str:
    """Return an adjective's positive en-form, even from a malformed comparison card."""
    candidates = [
        word,
        str(morphology.get("en_form", "")),
        str(morphology.get("ett_form", "")),
        str(morphology.get("plural_definite", "")),
        str(morphology.get("comparative", "")),
        str(morphology.get("superlative", "")),
    ]
    for candidate in candidates:
        irregular = _IRREGULAR_ADJECTIVE_LOOKUP.get(candidate.strip().lower())
        if irregular:
            return irregular

    current = word.strip().lower()
    comparative = str(morphology.get("comparative", "")).strip().lower()
    superlative = str(morphology.get("superlative", "")).strip().lower()
    comparison_forms = {comparative, superlative}
    if current not in comparison_forms:
        en_form = str(morphology.get("en_form", current)).strip().lower()
        return en_form or current
    if current.endswith("aste") and len(current) > 4:
        return current[:-4]
    if current.endswith("ast") and len(current) > 3:
        return current[:-3]
    if current.endswith("are") and len(current) > 3:
        return current[:-3]
    return current


def repaired_adjective_morphology(
    canonical_word: str, morphology: dict[str, Any]
) -> dict[str, Any]:
    """Repair comparison cards so every displayed form belongs to the base adjective."""
    irregular = _IRREGULAR_ADJECTIVES.get(canonical_word)
    if irregular:
        return dict(irregular)

    original_en = str(morphology.get("en_form", "")).strip().lower()
    comparative = str(morphology.get("comparative", "")).strip().lower()
    superlative = str(morphology.get("superlative", "")).strip().lower()
    was_comparison_card = (
        original_en in {comparative, superlative} and original_en != canonical_word
    )
    if not was_comparison_card:
        repaired = dict(morphology)
        repaired["type"] = "adjective"
        repaired["en_form"] = canonical_word
        return repaired

    ett_form = f"{canonical_word}t"
    plural = f"{canonical_word}a"
    return _adjective_forms(
        canonical_word,
        ett_form,
        plural,
        f"{canonical_word}are",
        f"{canonical_word}ast",
    )


def _strip_noun_article(value: str) -> str:
    """Remove an optional indefinite article from a noun dictionary form."""
    value = value.strip()
    lowered = value.lower()
    for article in ("en ", "ett "):
        if lowered.startswith(article):
            return value[len(article) :].strip()
    return value
