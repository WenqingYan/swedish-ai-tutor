"""Tests for data models — validation, serialization, and properties."""

from datetime import datetime

import pytest

from swedish_ai_tutor.models import (
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


class TestEpisode:
    """Test Episode model."""

    def test_create_episode(self) -> None:
        """Episode can be created with valid data."""
        ep = Episode(
            id=2838589,
            title="Klartext - nyheter på ett enklare sätt",
            description="Flera döda efter brand på krog i Thailand.",
            publish_date=datetime(2026, 7, 13, 18, 55, 0),
            audio_url="https://static-cdn.sr.se/test.mp3",
            duration_seconds=299,
            url="https://www.sverigesradio.se/avsnitt/2838589",
        )
        assert ep.id == 2838589
        assert ep.duration_seconds == 299

    def test_date_str_property(self) -> None:
        """date_str formats as YYYY-MM-DD."""
        ep = Episode(
            id=1,
            title="Test",
            description="Test",
            publish_date=datetime(2026, 7, 13, 18, 55, 0),
            audio_url="https://example.com/test.mp3",
            duration_seconds=300,
            url="https://example.com",
        )
        assert ep.date_str == "2026-07-13"

    def test_serialization_roundtrip(self) -> None:
        """Episode can serialize to JSON and back."""
        ep = Episode(
            id=123,
            title="Test",
            description="Desc",
            publish_date=datetime(2026, 1, 1, 12, 0, 0),
            audio_url="https://example.com/audio.mp3",
            duration_seconds=300,
            url="https://example.com",
        )
        json_str = ep.model_dump_json()
        ep2 = Episode.model_validate_json(json_str)
        assert ep2.id == ep.id
        assert ep2.publish_date == ep.publish_date


class TestTranscript:
    """Test Transcript model."""

    def test_sentences_split(self) -> None:
        """Transcript.sentences splits on sentence boundaries."""
        t = Transcript(
            full_text="Hej på dig. Hur mår du? Jag mår bra!",
        )
        assert t.sentences == ["Hej på dig.", "Hur mår du?", "Jag mår bra!"]

    def test_sentences_handles_multiple_spaces(self) -> None:
        """Sentence splitting handles irregular spacing."""
        t = Transcript(full_text="Första meningen.  Andra meningen.")
        assert t.sentences == ["Första meningen.", "Andra meningen."]

    def test_empty_text(self) -> None:
        """Empty text produces empty sentences list."""
        t = Transcript(full_text="")
        assert t.sentences == []

    def test_segments_optional(self) -> None:
        """Segments default to empty list."""
        t = Transcript(full_text="Hello")
        assert t.segments == []

    def test_segments_with_timing(self) -> None:
        """Segments can store timing information."""
        t = Transcript(
            full_text="Hello world",
            segments=[
                TranscriptSegment(text="Hello", start=0.0, end=1.0),
                TranscriptSegment(text="world", start=1.0, end=2.0),
            ],
        )
        assert len(t.segments) == 2
        assert t.segments[0].start == 0.0


class TestVocabularyEntry:
    """Test VocabularyEntry with morphology."""

    def test_verb_entry(self) -> None:
        """VocabularyEntry with verb morphology."""
        entry = VocabularyEntry(
            word="arbeta",
            pos="verb",
            meaning="工作",
            verb=VerbMorphology(
                group=1,
                imperative="arbeta",
                infinitive="arbeta",
                present="arbetar",
                past="arbetade",
                supine="arbetat",
            ),
        )
        assert entry.verb is not None
        assert entry.verb.group == 1
        assert entry.verb.present == "arbetar"
        assert entry.noun is None
        assert entry.adjective is None

    def test_noun_entry(self) -> None:
        """VocabularyEntry with noun morphology."""
        entry = VocabularyEntry(
            word="hund",
            pos="noun",
            meaning="狗",
            noun=NounMorphology(
                gender="en",
                indefinite_singular="en hund",
                definite_singular="hunden",
                indefinite_plural="hundar",
                definite_plural="hundarna",
            ),
        )
        assert entry.noun is not None
        assert entry.noun.gender == "en"
        assert entry.noun.definite_plural == "hundarna"

    def test_serialization_roundtrip(self) -> None:
        """VocabularyEntry can serialize to JSON and back."""
        entry = VocabularyEntry(
            word="stor",
            pos="adj",
            meaning="大的",
        )
        json_str = entry.model_dump_json()
        entry2 = VocabularyEntry.model_validate_json(json_str)
        assert entry2.word == "stor"


class TestSentenceAnalysis:
    """Test SentenceAnalysis model."""

    def test_create_full_analysis(self) -> None:
        """SentenceAnalysis with all fields populated."""
        analysis = SentenceAnalysis(
            original="Flera döda efter brand på krog i Thailand.",
            translation="泰国酒吧火灾致多人死亡。",
            grammar=GrammarNote(
                pattern="Noun phrase as subject",
                explanation="Swedish often uses noun phrases without a verb.",
                sfi_relevance="Common in news headlines",
            ),
            phrases=[
                Phrase(
                    phrase="flera döda",
                    meaning="多人死亡",
                    pattern_type="collocation",
                )
            ],
            vocabulary=[
                VocabularyEntry(word="brand", pos="noun", meaning="火灾"),
            ],
            examples=[
                ExampleSentence(
                    swedish="Flera skadade efter olyckan.",
                    chinese="事故中多人受伤。",
                ),
            ],
            sfi_notes="Headline style — common in reading comprehension texts.",
        )
        assert analysis.original.startswith("Flera")
        assert len(analysis.vocabulary) == 1
        assert len(analysis.phrases) == 1

    def test_defaults_for_optional_fields(self) -> None:
        """Optional fields default to empty."""
        analysis = SentenceAnalysis(
            original="Hej.",
            translation="你好。",
            grammar=GrammarNote(pattern="Interjection", explanation="打招呼"),
        )
        assert analysis.phrases == []
        assert analysis.vocabulary == []
        assert analysis.examples == []
        assert analysis.sfi_notes == ""


class TestLesson:
    """Test Lesson model."""

    @pytest.fixture()
    def sample_lesson(self) -> Lesson:
        """Create a sample lesson for testing."""
        return Lesson(
            episode=Episode(
                id=1,
                title="Test Episode",
                description="Test",
                publish_date=datetime(2026, 7, 13, 18, 55),
                audio_url="https://example.com/test.mp3",
                duration_seconds=300,
                url="https://example.com",
            ),
            transcript=Transcript(full_text="Hej. Hur mår du?"),
            analyses=[
                SentenceAnalysis(
                    original="Hej.",
                    translation="你好。",
                    grammar=GrammarNote(pattern="Greeting", explanation="打招呼"),
                    vocabulary=[
                        VocabularyEntry(word="hej", pos="interjection", meaning="你好"),
                    ],
                    phrases=[
                        Phrase(
                            phrase="hej på dig",
                            meaning="你好",
                            pattern_type="fixed_expression",
                        ),
                    ],
                ),
                SentenceAnalysis(
                    original="Hur mår du?",
                    translation="你好吗？",
                    grammar=GrammarNote(pattern="Question", explanation="提问句"),
                    vocabulary=[
                        VocabularyEntry(word="mår", pos="verb", meaning="感觉"),
                    ],
                ),
            ],
        )

    def test_sentence_count(self, sample_lesson: Lesson) -> None:
        """sentence_count returns number of analyzed sentences."""
        assert sample_lesson.sentence_count == 2

    def test_new_words(self, sample_lesson: Lesson) -> None:
        """new_words collects vocabulary from all sentences."""
        words = sample_lesson.new_words
        assert len(words) == 2
        assert words[0].word == "hej"
        assert words[1].word == "mår"

    def test_all_phrases(self, sample_lesson: Lesson) -> None:
        """all_phrases collects phrases from all sentences."""
        phrases = sample_lesson.all_phrases
        assert len(phrases) == 1
        assert phrases[0].phrase == "hej på dig"

    def test_serialization_roundtrip(self, sample_lesson: Lesson) -> None:
        """Full lesson can serialize to JSON and back."""
        json_str = sample_lesson.model_dump_json()
        lesson2 = Lesson.model_validate_json(json_str)
        assert lesson2.episode.id == 1
        assert lesson2.sentence_count == 2
