"""Sentence analyzer service — sends sentences to LLM and parses structured responses.

This is the core AI integration that transforms raw Swedish text
into structured learning material.
"""

import json
import logging

from openai import AsyncOpenAI

from swedish_ai_tutor.models.lesson import (
    AdjectiveMorphology,
    ExampleSentence,
    GrammarNote,
    NounMorphology,
    Phrase,
    SentenceAnalysis,
    VerbMorphology,
    VocabularyEntry,
)
from swedish_ai_tutor.models.transcript import Transcript
from swedish_ai_tutor.prompts import load_prompt, render_prompt

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class SentenceAnalyzer:
    """Analyzes Swedish sentences using an LLM to produce structured learning material.

    Loads the prompt template from the prompts directory, sends each sentence
    to the LLM with JSON mode, and parses the response into SentenceAnalysis objects.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        prompt_version: str = "v1",
        client: AsyncOpenAI | None = None,
    ) -> None:
        """Initialize the sentence analyzer.

        Args:
            api_key: OpenAI API key.
            model: LLM model name.
            prompt_version: Prompt template version to use.
            client: Optional pre-configured OpenAI client (for testing).
        """
        self._model = model
        self._client = client or AsyncOpenAI(api_key=api_key)
        self._prompt_version = prompt_version
        self._template = load_prompt(prompt_version, "sentence_analysis")

    async def analyze_sentence(self, sentence: str) -> SentenceAnalysis:
        """Analyze a single Swedish sentence.

        Sends the sentence to the LLM with the analysis prompt and
        parses the structured JSON response.

        Args:
            sentence: A single Swedish sentence to analyze.

        Returns:
            Structured analysis with grammar, phrases, vocabulary, etc.

        Raises:
            SentenceAnalysisError: If analysis fails after all retries.
        """
        prompt = render_prompt(self._template, sentence=sentence)

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a Swedish language teacher. "
                                "Always respond with valid JSON only."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )

                content = response.choices[0].message.content
                if not content:
                    msg = "Empty response from LLM"
                    raise SentenceAnalysisError(msg)

                return self._parse_response(content, sentence)

            except SentenceAnalysisError:
                if attempt == _MAX_RETRIES:
                    raise
                logger.warning(
                    "Analysis attempt %d/%d failed for: %s",
                    attempt, _MAX_RETRIES, sentence[:50],
                )
            except Exception as e:
                if attempt == _MAX_RETRIES:
                    msg = f"Failed to analyze sentence after {_MAX_RETRIES} attempts: {e}"
                    raise SentenceAnalysisError(msg) from e
                logger.warning(
                    "Analysis attempt %d/%d error: %s", attempt, _MAX_RETRIES, e
                )

        # Should never reach here, but satisfy type checker
        msg = "Unexpected analysis failure"
        raise SentenceAnalysisError(msg)  # pragma: no cover

    async def analyze_transcript(
        self, transcript: Transcript
    ) -> list[SentenceAnalysis]:
        """Analyze all sentences in a transcript.

        Processes sentences sequentially to respect API rate limits.
        Skips sentences that fail analysis after retries.

        Args:
            transcript: Full transcript to analyze.

        Returns:
            List of sentence analyses (may be shorter than sentences
            if some failed).
        """
        return await self.analyze_sentences(transcript.sentences)

    async def analyze_sentences(
        self, sentences: list[str]
    ) -> list[SentenceAnalysis]:
        """Analyze a list of sentences using batch mode for efficiency.

        Sends sentences in batches to reduce token overhead from repeated
        prompt instructions. Falls back to single-sentence mode on failure.

        Args:
            sentences: List of Swedish sentences to analyze.

        Returns:
            List of sentence analyses (may be shorter than input
            if some failed).
        """
        logger.info("Analyzing %d sentences", len(sentences))

        # Batch size: ~5-8 sentences per call balances token efficiency vs. reliability
        batch_size = 6
        results: list[SentenceAnalysis] = []

        for batch_start in range(0, len(sentences), batch_size):
            batch = sentences[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (len(sentences) + batch_size - 1) // batch_size
            logger.info(
                "Batch %d/%d: %d sentences",
                batch_num, total_batches, len(batch),
            )

            try:
                batch_results = await self._analyze_batch(batch)
                results.extend(batch_results)
            except SentenceAnalysisError:
                # Fallback: try sentences individually
                logger.warning("Batch failed, falling back to individual analysis")
                for sentence in batch:
                    try:
                        analysis = await self.analyze_sentence(sentence)
                        results.append(analysis)
                    except SentenceAnalysisError as e:
                        logger.error("Skipping sentence: %s", e)

        logger.info(
            "Analysis complete: %d/%d sentences successful",
            len(results), len(sentences),
        )
        return results

    async def _analyze_batch(self, sentences: list[str]) -> list[SentenceAnalysis]:
        """Analyze a batch of sentences in a single API call.

        Args:
            sentences: Batch of sentences (typically 5-8).

        Returns:
            List of analyses for the batch.

        Raises:
            SentenceAnalysisError: If batch analysis fails.
        """
        try:
            batch_template = load_prompt(self._prompt_version, "batch_sentence_analysis")
        except FileNotFoundError:
            # Fallback to sequential if batch prompt doesn't exist
            results: list[SentenceAnalysis] = []
            for sentence in sentences:
                results.append(await self.analyze_sentence(sentence))
            return results

        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
        prompt = render_prompt(batch_template, sentences=numbered)

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a Swedish language teacher. "
                                "Respond with valid JSON only."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )

                content = response.choices[0].message.content
                if not content:
                    msg = "Empty response from LLM"
                    raise SentenceAnalysisError(msg)

                return self._parse_batch_response(content, sentences)

            except SentenceAnalysisError:
                if attempt == _MAX_RETRIES:
                    raise
                logger.warning("Batch attempt %d/%d failed", attempt, _MAX_RETRIES)
            except Exception as e:
                if attempt == _MAX_RETRIES:
                    msg = f"Batch analysis failed after {_MAX_RETRIES} attempts: {e}"
                    raise SentenceAnalysisError(msg) from e
                logger.warning("Batch attempt %d/%d error: %s", attempt, _MAX_RETRIES, e)

        msg = "Unexpected batch failure"
        raise SentenceAnalysisError(msg)  # pragma: no cover

    def _parse_batch_response(
        self, content: str, original_sentences: list[str]
    ) -> list[SentenceAnalysis]:
        """Parse a batch JSON response containing multiple sentence analyses.

        Args:
            content: Raw JSON from LLM with {"analyses": [...]}.
            original_sentences: Original sentences for fallback.

        Returns:
            List of parsed SentenceAnalysis objects.

        Raises:
            SentenceAnalysisError: If JSON is invalid.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON from batch LLM response: {e}"
            raise SentenceAnalysisError(msg) from e

        analyses_data = data.get("analyses", [])
        if not analyses_data:
            msg = "Batch response has no 'analyses' field"
            raise SentenceAnalysisError(msg)

        results: list[SentenceAnalysis] = []
        for i, item in enumerate(analyses_data):
            fallback = original_sentences[i] if i < len(original_sentences) else ""
            try:
                # Reuse existing single-item parser logic
                grammar = GrammarNote(
                    pattern=item.get("grammar", {}).get("pattern", ""),
                    explanation=item.get("grammar", {}).get("explanation", ""),
                    sfi_relevance=item.get("grammar", {}).get("sfi_relevance", ""),
                )
                phrases = [
                    Phrase(
                        phrase=p.get("phrase", ""),
                        meaning=p.get("meaning", ""),
                        pattern_type=p.get("pattern_type", "collocation"),
                        example=p.get("example", ""),
                    )
                    for p in item.get("phrases", [])
                ]
                vocabulary = [
                    self._parse_vocabulary_entry(v)
                    for v in item.get("vocabulary", [])
                ]
                results.append(SentenceAnalysis(
                    original=item.get("original", fallback),
                    translation=item.get("translation", ""),
                    grammar=grammar,
                    phrases=phrases,
                    vocabulary=vocabulary,
                    examples=self._parse_examples(item.get("examples", [])),
                    sfi_notes=item.get("sfi_notes", ""),
                ))
            except Exception as e:
                logger.warning("Failed to parse sentence %d in batch: %s", i + 1, e)

        return results

    def _parse_response(self, content: str, original_sentence: str) -> SentenceAnalysis:
        """Parse LLM JSON response into a SentenceAnalysis model.

        Args:
            content: Raw JSON string from LLM.
            original_sentence: The original sentence (fallback if LLM changes it).

        Returns:
            Validated SentenceAnalysis model.

        Raises:
            SentenceAnalysisError: If JSON is invalid or missing required fields.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON from LLM: {e}"
            raise SentenceAnalysisError(msg) from e

        try:
            grammar = GrammarNote(
                pattern=data.get("grammar", {}).get("pattern", ""),
                explanation=data.get("grammar", {}).get("explanation", ""),
                sfi_relevance=data.get("grammar", {}).get("sfi_relevance", ""),
            )

            phrases = [
                Phrase(
                    phrase=p.get("phrase", ""),
                    meaning=p.get("meaning", ""),
                    pattern_type=p.get("pattern_type", "collocation"),
                    example=p.get("example", ""),
                )
                for p in data.get("phrases", [])
            ]

            vocabulary = [
                self._parse_vocabulary_entry(v)
                for v in data.get("vocabulary", [])
            ]

            return SentenceAnalysis(
                original=data.get("original", original_sentence),
                translation=data.get("translation", ""),
                grammar=grammar,
                phrases=phrases,
                vocabulary=vocabulary,
                examples=self._parse_examples(data.get("examples", [])),
                sfi_notes=data.get("sfi_notes", ""),
            )
        except Exception as e:
            msg = f"Failed to parse LLM response structure: {e}"
            raise SentenceAnalysisError(msg) from e

    def _parse_vocabulary_entry(self, data: dict) -> VocabularyEntry:  # type: ignore[type-arg]
        """Parse a single vocabulary entry from LLM response.

        Args:
            data: Dict with word, pos, meaning, and optional morphology.

        Returns:
            VocabularyEntry with appropriate morphology attached.
        """
        verb = None
        noun = None
        adjective = None

        if data.get("verb"):
            verb_data = data["verb"]
            verb = VerbMorphology(
                group=verb_data.get("group", 1),
                imperative=verb_data.get("imperative", ""),
                infinitive=verb_data.get("infinitive", ""),
                present=verb_data.get("present", ""),
                past=verb_data.get("past", ""),
                supine=verb_data.get("supine", ""),
            )

        if data.get("noun"):
            noun_data = data["noun"]
            noun = NounMorphology(
                gender=noun_data.get("gender", "en"),
                indefinite_singular=noun_data.get("indefinite_singular", ""),
                definite_singular=noun_data.get("definite_singular", ""),
                indefinite_plural=noun_data.get("indefinite_plural", ""),
                definite_plural=noun_data.get("definite_plural", ""),
            )

        if data.get("adjective"):
            adj_data = data["adjective"]
            adjective = AdjectiveMorphology(
                en_form=adj_data.get("en_form", ""),
                ett_form=adj_data.get("ett_form", ""),
                plural_definite=adj_data.get("plural_definite", ""),
                comparative=adj_data.get("comparative", ""),
                superlative=adj_data.get("superlative", ""),
            )

        return VocabularyEntry(
            word=data.get("word", ""),
            pos=data.get("pos", ""),
            meaning=data.get("meaning", ""),
            verb=verb,
            noun=noun,
            adjective=adjective,
        )

    def _parse_examples(self, raw: list) -> list[ExampleSentence]:  # type: ignore[type-arg]
        """Parse examples from LLM response.

        Handles both new format (list of dicts with swedish/chinese)
        and old format (list of plain strings) for backward compatibility.

        Args:
            raw: Raw examples list from LLM JSON.

        Returns:
            List of ExampleSentence objects.
        """
        results: list[ExampleSentence] = []
        for item in raw:
            if isinstance(item, dict):
                results.append(ExampleSentence(
                    swedish=item.get("swedish", ""),
                    chinese=item.get("chinese", ""),
                ))
            elif isinstance(item, str):
                # Backward compat: plain string → no translation
                results.append(ExampleSentence(swedish=item, chinese=""))
        return results


class SentenceAnalysisError(Exception):
    """Raised when sentence analysis fails."""
