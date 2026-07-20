"""Data models for LLM-generated learning material."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, model_validator

from swedish_ai_tutor.models.episode import Episode
from swedish_ai_tutor.models.transcript import Transcript


class VerbMorphology(BaseModel):
    """Complete verb conjugation (Swedish verb groups 1-4)."""

    group: int = Field(description="Verb group (1-4)")
    imperative: str = Field(default="", description="Imperativ")
    infinitive: str = Field(description="Infinitiv")
    present: str = Field(description="Presens")
    past: str = Field(description="Preteritum")
    supine: str = Field(description="Supinum")


class NounMorphology(BaseModel):
    """Complete noun declension."""

    gender: str = Field(description="en or ett")
    indefinite_singular: str = Field(description="Obestämd singular")
    definite_singular: str = Field(description="Bestämd singular")
    indefinite_plural: str = Field(description="Obestämd plural")
    definite_plural: str = Field(description="Bestämd plural")


class AdjectiveMorphology(BaseModel):
    """Complete adjective declension."""

    en_form: str = Field(description="en-form (utrum singular)")
    ett_form: str = Field(description="ett-form (neutrum singular)")
    plural_definite: str = Field(description="Plural/bestämd form")
    comparative: str = Field(default="", description="Komparativ")
    superlative: str = Field(default="", description="Superlativ")


class VocabularyEntry(BaseModel):
    """A single vocabulary item with meaning and morphology."""

    word: str = Field(description="Swedish word (base/dictionary form)")
    pos: str = Field(description="Part of speech (verb, noun, adj, adv, etc.)")
    meaning: str = Field(description="Chinese translation/meaning")
    verb: VerbMorphology | None = Field(default=None, description="Verb forms (if verb)")
    noun: NounMorphology | None = Field(default=None, description="Noun forms (if noun)")
    adjective: AdjectiveMorphology | None = Field(
        default=None, description="Adjective forms (if adjective)"
    )


class Phrase(BaseModel):
    """A reusable multi-word expression or collocation."""

    phrase: str = Field(description="Swedish phrase")
    meaning: str = Field(description="Chinese meaning")
    pattern_type: str = Field(
        default="collocation",
        description="Type: collocation, idiom, fixed_expression, verb_particle",
    )
    example: str = Field(default="", description="Example sentence using the phrase")


class GrammarNote(BaseModel):
    """A grammar pattern identified in a sentence."""

    pattern: str = Field(description="Name of the grammar pattern (e.g., 'V2 word order')")
    explanation: str = Field(description="Chinese explanation of why this pattern is used")
    sfi_relevance: str = Field(
        default="", description="How this relates to SFI C/D exam"
    )


class ExampleSentence(BaseModel):
    """An example sentence with translation to reinforce a pattern."""

    swedish: str = Field(description="Swedish example sentence")
    chinese: str = Field(description="Chinese translation")


class SentenceAnalysis(BaseModel):
    """Complete analysis of a single Swedish sentence.

    This is the core learning unit — one sentence fully broken down.
    """

    original: str = Field(description="Original Swedish sentence")
    translation: str = Field(description="Chinese translation (natural, not word-by-word)")
    grammar: GrammarNote = Field(description="Key grammar pattern in this sentence")
    phrases: list[Phrase] = Field(
        default_factory=list, description="Reusable phrases identified"
    )
    vocabulary: list[VocabularyEntry] = Field(
        default_factory=list, description="Notable vocabulary with morphology"
    )
    examples: list[ExampleSentence] = Field(
        default_factory=list,
        description="Example sentences with Chinese translation",
    )
    sfi_notes: str = Field(default="", description="SFI exam tips related to this sentence")

    @model_validator(mode="before")
    @classmethod
    def _convert_legacy_examples(cls, data: object) -> object:
        """Convert old-format examples (list of strings) to ExampleSentence objects."""
        if isinstance(data, dict) and "examples" in data:
            examples = data["examples"]
            if examples and isinstance(examples[0], str):
                data["examples"] = [
                    {"swedish": s, "chinese": ""} for s in examples
                ]
        return data


class NewsStory(BaseModel):
    """A single news story within an episode, with its headline and analyzed sentences."""

    headline: str = Field(description="Story topic/headline from episode description")
    analyses: list[SentenceAnalysis] = Field(
        description="Analyzed sentences belonging to this story"
    )


class Lesson(BaseModel):
    """A complete daily lesson generated from one episode.

    This is the top-level output of the pipeline — ready to export to Notion.
    """

    episode: Episode = Field(description="Source episode metadata")
    transcript: Transcript = Field(description="Full transcription")
    analyses: list[SentenceAnalysis] = Field(
        default_factory=list,
        description="Per-sentence analysis results (flat list, for backward compat)",
    )
    stories: list[NewsStory] = Field(
        default_factory=list,
        description="Analyses grouped by news story with headlines",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this lesson was generated",
    )

    @property
    def all_analyses(self) -> list[SentenceAnalysis]:
        """All analyses — from stories if available, otherwise flat list."""
        if self.stories:
            result: list[SentenceAnalysis] = []
            for story in self.stories:
                result.extend(story.analyses)
            return result
        return self.analyses

    @property
    def new_words(self) -> list[VocabularyEntry]:
        """All vocabulary entries across all sentences (may have duplicates)."""
        words: list[VocabularyEntry] = []
        for analysis in self.all_analyses:
            words.extend(analysis.vocabulary)
        return words

    @property
    def all_phrases(self) -> list[Phrase]:
        """All phrases across all sentences."""
        phrases: list[Phrase] = []
        for analysis in self.all_analyses:
            phrases.extend(analysis.phrases)
        return phrases

    @property
    def sentence_count(self) -> int:
        """Number of sentences analyzed."""
        return len(self.all_analyses)
