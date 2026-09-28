"""Tests for the transcription service."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from swedish_ai_tutor.services.transcriber import (
    IncompleteTranscriptionError,
    WhisperAPITranscriber,
    assess_transcription,
)


class MockSegment:
    """Mock a Whisper API segment."""

    def __init__(self, text: str, start: float, end: float, speaker: str | None = None) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.speaker = speaker


class MockTranscriptionResponse:
    """Mock the Whisper API verbose_json response."""

    def __init__(
        self, text: str, segments: list[MockSegment], duration: float = 0.0
    ) -> None:
        self.text = text
        self.segments = segments
        self.duration = duration


class TestWhisperAPITranscriber:
    """Test WhisperAPITranscriber with mocked OpenAI client."""

    @pytest.fixture()
    def mock_client(self) -> AsyncMock:
        """Create a mocked OpenAI async client."""
        client = AsyncMock()
        return client

    @pytest.fixture()
    def audio_file(self, tmp_path: Path) -> Path:
        """Create a fake audio file for testing."""
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"\xff\xfb\x90\x00" * 50)
        return audio

    @pytest.mark.asyncio()
    async def test_transcribe_success(self, mock_client: AsyncMock, audio_file: Path) -> None:
        """Successful transcription returns Transcript with text and segments."""
        mock_response = MockTranscriptionResponse(
            text="Hej, det här är nyheter på lätt svenska.",
            segments=[
                MockSegment("Hej, det här är", 0.0, 2.5),
                MockSegment("nyheter på lätt svenska.", 2.5, 5.0),
            ],
        )
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        transcriber = WhisperAPITranscriber(api_key="test-key", client=mock_client)
        transcript = await transcriber.transcribe(audio_file)

        assert transcript.full_text == "Hej, det här är nyheter på lätt svenska."
        assert len(transcript.segments) == 2
        assert transcript.segments[0].text == "Hej, det här är"
        assert transcript.segments[0].start == 0.0
        assert transcript.segments[1].end == 5.0
        assert transcript.language == "sv"

    @pytest.mark.asyncio()
    async def test_transcribe_no_segments(self, mock_client: AsyncMock, audio_file: Path) -> None:
        """Transcription without segments returns empty segments list."""
        mock_response = MagicMock()
        mock_response.text = "Bara text utan segment."
        mock_response.segments = None
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        transcriber = WhisperAPITranscriber(api_key="test-key", client=mock_client)
        transcript = await transcriber.transcribe(audio_file)

        assert transcript.full_text == "Bara text utan segment."
        assert transcript.segments == []

    @pytest.mark.asyncio()
    async def test_transcribe_file_not_found(self, mock_client: AsyncMock) -> None:
        """Raises FileNotFoundError for missing audio file."""
        transcriber = WhisperAPITranscriber(api_key="test-key", client=mock_client)

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            await transcriber.transcribe(Path("/nonexistent/audio.mp3"))

    @pytest.mark.asyncio()
    async def test_transcribe_passes_correct_params(
        self, mock_client: AsyncMock, audio_file: Path
    ) -> None:
        """Verifies correct parameters passed to Whisper API."""
        mock_response = MagicMock()
        mock_response.text = "Test"
        mock_response.segments = []
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        transcriber = WhisperAPITranscriber(
            api_key="test-key",
            model="whisper-1",
            language="sv",
            client=mock_client,
        )
        await transcriber.transcribe(audio_file)

        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["language"] == "sv"
        assert call_kwargs["response_format"] == "verbose_json"
        assert "intervju" in call_kwargs["prompt"]

    @pytest.mark.asyncio()
    async def test_diarized_model_preserves_speakers_and_uses_chunking(
        self, mock_client: AsyncMock, audio_file: Path
    ) -> None:
        """Interview transcription keeps speaker labels and enables audio chunking."""
        mock_response = MockTranscriptionResponse(
            text="Hur känns det? Det känns bra.",
            segments=[
                MockSegment("Hur känns det?", 1.0, 2.0, "A"),
                MockSegment("Det känns bra.", 2.0, 3.0, "B"),
            ],
        )
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
        transcriber = WhisperAPITranscriber(
            api_key="test-key",
            model="gpt-4o-transcribe-diarize",
            client=mock_client,
        )

        transcript = await transcriber.transcribe(audio_file)

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["response_format"] == "diarized_json"
        assert call_kwargs["chunking_strategy"] == "auto"
        assert "timestamp_granularities" not in call_kwargs
        assert transcript.segments[0].speaker == "A"
        assert transcript.segments[1].speaker == "B"

    @pytest.mark.asyncio()
    async def test_transcribe_filters_empty_segments(
        self, mock_client: AsyncMock, audio_file: Path
    ) -> None:
        """Empty/whitespace-only segments are filtered out."""
        mock_response = MockTranscriptionResponse(
            text="Hello world",
            segments=[
                MockSegment("Hello", 0.0, 1.0),
                MockSegment("   ", 1.0, 1.5),  # whitespace only
                MockSegment("world", 1.5, 2.5),
            ],
        )
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        transcriber = WhisperAPITranscriber(api_key="test-key", client=mock_client)
        transcript = await transcriber.transcribe(audio_file)

        assert len(transcript.segments) == 2
        assert transcript.segments[0].text == "Hello"
        assert transcript.segments[1].text == "world"

    def test_quality_check_detects_large_timeline_hole(self) -> None:
        """A long missing region is rejected even when text exists before and after it."""
        segments = [
            MockSegment("Första delen " * 30, 0.0, 40.0),
            MockSegment("Sista delen " * 30, 85.0, 120.0),
        ]
        parsed = WhisperAPITranscriber("test")._parse_segments(  # noqa: SLF001
            MockTranscriptionResponse("", segments)
        )
        quality = assess_transcription(" ".join(item.text for item in segments), parsed, 120)

        assert quality.suspicious
        assert quality.largest_gap == 45
        assert "timeline gap" in " ".join(quality.reasons)

    @pytest.mark.asyncio()
    async def test_incomplete_diarized_result_uses_complete_fallback(
        self, mock_client: AsyncMock, audio_file: Path
    ) -> None:
        """Large omissions trigger one independent non-diarized transcription."""
        incomplete = MockTranscriptionResponse(
            text="Kort början.",
            segments=[MockSegment("Kort början.", 0.0, 8.0, "A")],
            duration=180.0,
        )
        complete_text = "Det här är en fullständig svensk utskrift. " * 80
        complete = MockTranscriptionResponse(
            text=complete_text,
            segments=[MockSegment(complete_text, 0.0, 180.0)],
            duration=180.0,
        )
        mock_client.audio.transcriptions.create = AsyncMock(
            side_effect=[incomplete, complete]
        )
        transcriber = WhisperAPITranscriber(
            "test",
            model="gpt-4o-transcribe-diarize",
            fallback_model="whisper-1",
            client=mock_client,
        )

        transcript = await transcriber.transcribe(audio_file)

        assert transcript.full_text == complete_text
        calls = mock_client.audio.transcriptions.create.call_args_list
        assert calls[0].kwargs["model"] == "gpt-4o-transcribe-diarize"
        assert calls[1].kwargs["model"] == "whisper-1"
        assert calls[1].kwargs["response_format"] == "verbose_json"

    @pytest.mark.asyncio()
    async def test_incomplete_fallback_stops_pipeline_data_creation(
        self, mock_client: AsyncMock, audio_file: Path
    ) -> None:
        """Two incomplete responses raise instead of silently returning bad text."""
        incomplete = MockTranscriptionResponse(
            text="För kort.",
            segments=[MockSegment("För kort.", 0.0, 5.0)],
            duration=180.0,
        )
        mock_client.audio.transcriptions.create = AsyncMock(
            side_effect=[incomplete, incomplete]
        )
        transcriber = WhisperAPITranscriber(
            "test", model="gpt-4o-transcribe-diarize", client=mock_client
        )

        with pytest.raises(IncompleteTranscriptionError, match="completeness checks"):
            await transcriber.transcribe(audio_file)
