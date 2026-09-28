"""LLM-backed enrichment for manually entered Swedish vocabulary."""

import json

from openai import AsyncOpenAI
from pydantic import BaseModel

from swedish_ai_tutor.models.lesson import ExampleSentence, VocabularyEntry
from swedish_ai_tutor.prompts import load_prompt, render_prompt
from swedish_ai_tutor.services.sentence_analyzer import SentenceAnalyzer


class EnrichedWord(BaseModel):
    """A complete review card returned by the vocabulary enrichment API."""

    entry: VocabularyEntry
    example: ExampleSentence


class WordEnrichmentError(RuntimeError):
    """Raised when the API cannot produce a valid vocabulary card."""


class WordEnricher:
    """Generate meaning, morphology, and an example for one Swedish word."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        prompt_version: str = "v1",
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._client = client or AsyncOpenAI(api_key=api_key)
        self._template = load_prompt(prompt_version, "word_enrichment")

    async def enrich(self, word: str, pos: str = "unknown", meaning: str = "") -> EnrichedWord:
        """Return a fully populated vocabulary card for ``word``."""
        prompt = render_prompt(
            self._template,
            word=word.strip(),
            pos=pos.strip() or "unknown",
            meaning=meaning.strip(),
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise Swedish lexicographer. Return valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = response.choices[0].message.content
            if not content:
                raise WordEnrichmentError("The API returned an empty response")
            data = json.loads(content)
            entry = SentenceAnalyzer._parse_vocabulary_entry(data)  # noqa: SLF001
            example = ExampleSentence.model_validate(data.get("example", {}))
        except WordEnrichmentError:
            raise
        except Exception as exc:
            raise WordEnrichmentError(f"Could not enrich '{word}': {exc}") from exc

        if not entry.word or not entry.pos or not entry.meaning:
            raise WordEnrichmentError("The API response is missing word, POS, or meaning")
        if not example.swedish or not example.chinese:
            raise WordEnrichmentError("The API response is missing the bilingual example")
        return EnrichedWord(entry=entry, example=example)
