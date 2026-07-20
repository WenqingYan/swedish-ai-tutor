"""Tests for the sentence analyzer service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from swedish_ai_tutor.models.transcript import Transcript
from swedish_ai_tutor.services.sentence_analyzer import (
    SentenceAnalysisError,
    SentenceAnalyzer,
)

# Sample LLM response that matches our expected JSON schema
SAMPLE_LLM_RESPONSE = json.dumps({
    "original": "Flera döda efter brand på krog i Thailand.",
    "translation": "泰国酒吧火灾致多人死亡。",
    "grammar": {
        "pattern": "Noun phrase as headline",
        "explanation": "瑞典语新闻标题常省略主动词，直接使用名词短语表达事件。",
        "sfi_relevance": "SFI D阅读理解中常见新闻标题风格。",
    },
    "phrases": [
        {
            "phrase": "flera döda",
            "meaning": "多人死亡",
            "pattern_type": "collocation",
            "example": "Flera döda i trafikolycka.",
        }
    ],
    "vocabulary": [
        {
            "word": "brand",
            "pos": "noun",
            "meaning": "火灾",
            "verb": None,
            "noun": {
                "gender": "en",
                "indefinite_singular": "en brand",
                "definite_singular": "branden",
                "indefinite_plural": "bränder",
                "definite_plural": "bränderna",
            },
            "adjective": None,
        },
        {
            "word": "krog",
            "pos": "noun",
            "meaning": "酒吧/餐馆",
            "verb": None,
            "noun": {
                "gender": "en",
                "indefinite_singular": "en krog",
                "definite_singular": "krogen",
                "indefinite_plural": "krogar",
                "definite_plural": "krogarna",
            },
            "adjective": None,
        },
    ],
    "examples": ["Flera skadade efter olyckan på motorvägen."],
    "sfi_notes": "新闻标题风格在SFI D级阅读理解中经常出现，注意省略动词的句式。",
})


def _make_mock_client(response_content: str) -> AsyncMock:
    """Create a mock OpenAI client that returns the given content."""
    client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = response_content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client


class TestSentenceAnalyzer:
    """Test sentence analyzer with mocked LLM responses."""

    @pytest.mark.asyncio()
    async def test_analyze_sentence_success(self) -> None:
        """Successfully analyzes a sentence and returns structured data."""
        mock_client = _make_mock_client(SAMPLE_LLM_RESPONSE)
        analyzer = SentenceAnalyzer(api_key="test", client=mock_client)

        result = await analyzer.analyze_sentence(
            "Flera döda efter brand på krog i Thailand."
        )

        assert result.original == "Flera döda efter brand på krog i Thailand."
        assert result.translation == "泰国酒吧火灾致多人死亡。"
        assert result.grammar.pattern == "Noun phrase as headline"
        assert len(result.phrases) == 1
        assert result.phrases[0].phrase == "flera döda"
        assert len(result.vocabulary) == 2
        assert result.vocabulary[0].word == "brand"
        assert result.vocabulary[0].noun is not None
        assert result.vocabulary[0].noun.gender == "en"
        assert result.vocabulary[0].noun.definite_plural == "bränderna"
        assert len(result.examples) == 1
        assert result.sfi_notes != ""

    @pytest.mark.asyncio()
    async def test_analyze_sentence_with_verb(self) -> None:
        """Correctly parses verb morphology."""
        response = json.dumps({
            "original": "Hon arbetar på sjukhuset.",
            "translation": "她在医院工作。",
            "grammar": {
                "pattern": "SVO word order",
                "explanation": "主语+动词+地点状语",
                "sfi_relevance": "",
            },
            "phrases": [],
            "vocabulary": [
                {
                    "word": "arbeta",
                    "pos": "verb",
                    "meaning": "工作",
                    "verb": {
                        "group": 1,
                        "imperative": "arbeta",
                        "infinitive": "arbeta",
                        "present": "arbetar",
                        "past": "arbetade",
                        "supine": "arbetat",
                    },
                    "noun": None,
                    "adjective": None,
                }
            ],
            "examples": [],
            "sfi_notes": "",
        })
        mock_client = _make_mock_client(response)
        analyzer = SentenceAnalyzer(api_key="test", client=mock_client)

        result = await analyzer.analyze_sentence("Hon arbetar på sjukhuset.")

        assert result.vocabulary[0].verb is not None
        assert result.vocabulary[0].verb.group == 1
        assert result.vocabulary[0].verb.present == "arbetar"
        assert result.vocabulary[0].verb.supine == "arbetat"
        assert result.vocabulary[0].noun is None

    @pytest.mark.asyncio()
    async def test_analyze_sentence_invalid_json(self) -> None:
        """Raises SentenceAnalysisError on invalid JSON response."""
        mock_client = _make_mock_client("This is not JSON")
        analyzer = SentenceAnalyzer(api_key="test", client=mock_client)

        with pytest.raises(SentenceAnalysisError, match="Invalid JSON"):
            await analyzer.analyze_sentence("Test sentence.")

    @pytest.mark.asyncio()
    async def test_analyze_sentence_empty_response(self) -> None:
        """Raises SentenceAnalysisError on empty response."""
        client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        client.chat.completions.create = AsyncMock(return_value=mock_response)

        analyzer = SentenceAnalyzer(api_key="test", client=client)

        with pytest.raises(SentenceAnalysisError, match="Empty response"):
            await analyzer.analyze_sentence("Test.")

    @pytest.mark.asyncio()
    async def test_analyze_sentence_retries_on_failure(self) -> None:
        """Retries on transient errors before raising."""
        client = AsyncMock()
        # First call fails, second succeeds
        mock_choice = MagicMock()
        mock_choice.message.content = SAMPLE_LLM_RESPONSE
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        client.chat.completions.create = AsyncMock(
            side_effect=[
                RuntimeError("Timeout"),
                mock_response,
            ]
        )

        analyzer = SentenceAnalyzer(api_key="test", client=client)
        result = await analyzer.analyze_sentence("Test sentence.")

        assert result.original == "Flera döda efter brand på krog i Thailand."
        assert client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio()
    async def test_analyze_transcript(self) -> None:
        """Analyzes all sentences in a transcript via batch mode."""
        # Mock returns a batch response format
        batch_response = json.dumps({
            "analyses": [
                json.loads(SAMPLE_LLM_RESPONSE),
                json.loads(SAMPLE_LLM_RESPONSE),
                json.loads(SAMPLE_LLM_RESPONSE),
            ]
        })
        mock_client = _make_mock_client(batch_response)
        analyzer = SentenceAnalyzer(api_key="test", client=mock_client)

        transcript = Transcript(
            full_text="Första meningen. Andra meningen. Tredje meningen."
        )
        results = await analyzer.analyze_transcript(transcript)

        assert len(results) == 3
        # Batch mode: 1 call for all 3 sentences (batch size 6 > 3)
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio()
    async def test_analyze_transcript_falls_back_on_batch_failure(self) -> None:
        """Falls back to individual analysis when batch fails."""
        client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = SAMPLE_LLM_RESPONSE
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        # First 3 calls fail (batch retries), then 3 succeed (individual fallback)
        client.chat.completions.create = AsyncMock(
            side_effect=[
                RuntimeError("Batch fail"),
                RuntimeError("Batch fail"),
                RuntimeError("Batch fail"),
                mock_response,  # sentence 1 individual
                mock_response,  # sentence 2 individual
                mock_response,  # sentence 3 individual
            ]
        )

        analyzer = SentenceAnalyzer(api_key="test", client=client)
        transcript = Transcript(full_text="One. Two. Three.")
        results = await analyzer.analyze_transcript(transcript)

        assert len(results) == 3

    @pytest.mark.asyncio()
    async def test_passes_correct_model(self) -> None:
        """Verifies the configured model is passed to the API."""
        mock_client = _make_mock_client(SAMPLE_LLM_RESPONSE)
        analyzer = SentenceAnalyzer(
            api_key="test", model="gpt-4o-mini", client=mock_client
        )

        await analyzer.analyze_sentence("Test.")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["response_format"] == {"type": "json_object"}
