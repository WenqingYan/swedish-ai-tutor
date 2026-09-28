"""Tests for API-backed manual vocabulary enrichment."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swedish_ai_tutor.services.word_enricher import WordEnricher, WordEnrichmentError


def _client_with_response(data: dict[str, object]) -> AsyncMock:
    """Build an OpenAI-like async client returning one JSON response."""
    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))]
    )
    return client


@pytest.mark.asyncio
async def test_enriches_verb_with_example() -> None:
    """A valid API response becomes a typed complete review card."""
    client = _client_with_response(
        {
            "word": "utreda",
            "pos": "verb",
            "meaning": "调查",
            "verb": {
                "group": 2,
                "imperative": "utred",
                "infinitive": "utreda",
                "present": "utreder",
                "past": "utredde",
                "supine": "utrett",
            },
            "noun": None,
            "adjective": None,
            "example": {
                "swedish": "Polisen ska utreda olyckan.",
                "chinese": "警方将调查这起事故。",
            },
        }
    )

    result = await WordEnricher("test", client=client).enrich("utreda")

    assert result.entry.verb is not None
    assert result.entry.verb.supine == "utrett"
    assert result.example.chinese == "警方将调查这起事故。"


@pytest.mark.asyncio
async def test_rejects_incomplete_example() -> None:
    """An incomplete response is not allowed to create a partial card."""
    client = _client_with_response(
        {
            "word": "snabb",
            "pos": "adj",
            "meaning": "快的",
            "example": {"swedish": "Bussen är snabb.", "chinese": ""},
        }
    )

    with pytest.raises(WordEnrichmentError, match="bilingual example"):
        await WordEnricher("test", client=client).enrich("snabb")
