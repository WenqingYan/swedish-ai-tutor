"""Tests for deterministic news-story segmentation."""

from swedish_ai_tutor.models.transcript import TranscriptSegment
from swedish_ai_tutor.services.pipeline import (
    _parse_story_headlines,
    _segment_stories,
)


def test_generic_programme_description_is_not_a_story_headline() -> None:
    description = "Nyheter på lätt svenska för dig som är ny i Sverige."

    assert _parse_story_headlines(description) == []


def test_slash_separated_story_headlines_are_preserved() -> None:
    description = "Brand i Linköping / Fler handlar secondhand / Man räddar katter"

    assert _parse_story_headlines(description) == [
        "Brand i Linköping",
        "Fler handlar secondhand",
        "Man räddar katter",
    ]


def test_generic_episode_uses_topic_openers_and_audio_pauses() -> None:
    sentences = [
        "Radio Sweden på lätt svenska med Nina och Jenny.",
        "Fredag den 31 juli.",
        "Det började brinna i ett bostadshus.",
        "Många personer fick lämna sina hem.",
        "Polisen kom mitt i natten.",
        "Ingen person blev skadad.",
        "Nu kan svenskar utomlands rösta i valet.",
        "De kan rösta med brev.",
        "Flera partier vill nå dem.",
        "De kan bli viktiga väljare.",
        "Nu på sommaren handlar fler secondhand.",
        "Många är lediga.",
        "En del letar saker till sommarstugan.",
        "Det kan också vara billigare.",
        "Teddy har räddat många katter från träd.",
        "Han arbetar som klättrare.",
        "Han vill hjälpa fler djur.",
        "Han hoppas att andra lär sig.",
        "Radio Sweden på lätt svenska.",
        "Läs också våra texter i appen Sveriges Radio.",
        "gu.se",
    ]
    segments = [
        TranscriptSegment(text=sentence, start=float(index * 5), end=float(index * 5 + 4))
        for index, sentence in enumerate(sentences)
    ]
    # A four-second gap before Teddy marks a story transition without "Nu".
    for index in range(14, len(segments)):
        segments[index].start += 3
        segments[index].end += 3

    groups = _segment_stories(sentences, [], segments)

    assert len(groups) == 4
    assert [group[0] for group in groups] == [
        "Det började brinna i ett bostadshus.",
        "Nu kan svenskar utomlands rösta i valet.",
        "Nu på sommaren handlar fler secondhand.",
        "Teddy har räddat många katter från träd.",
    ]
    assert groups[-1][-1] == "Han hoppas att andra lär sig."
