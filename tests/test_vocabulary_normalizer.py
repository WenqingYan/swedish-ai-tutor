"""Tests for stable vocabulary identities."""

from swedish_ai_tutor.models.lesson import (
    AdjectiveMorphology,
    NounMorphology,
    VerbMorphology,
    VocabularyEntry,
)
from swedish_ai_tutor.services.vocabulary_normalizer import canonicalize_entry


def test_inflected_verb_uses_infinitive() -> None:
    entry = VocabularyEntry(
        word="berättar",
        pos="verb",
        meaning="讲述",
        verb=VerbMorphology(
            group=1,
            imperative="berätta",
            infinitive="berätta",
            present="berättar",
            past="berättade",
            supine="berättat",
        ),
    )
    assert canonicalize_entry(entry).word == "berätta"


def test_plural_noun_uses_article_free_singular() -> None:
    entry = VocabularyEntry(
        word="annonserna",
        pos="noun",
        meaning="广告",
        noun=NounMorphology(
            gender="en",
            indefinite_singular="en annons",
            definite_singular="annonsen",
            indefinite_plural="annonser",
            definite_plural="annonserna",
        ),
    )
    assert canonicalize_entry(entry).word == "annons"


def test_adjective_and_pos_alias_are_normalized() -> None:
    entry = VocabularyEntry(
        word="farligaste",
        pos="adjective",
        meaning="危险的",
        adjective=AdjectiveMorphology(
            en_form="farlig",
            ett_form="farligt",
            plural_definite="farliga",
            comparative="farligare",
            superlative="farligast",
        ),
    )
    result = canonicalize_entry(entry)
    assert (result.word, result.pos) == ("farlig", "adj")
