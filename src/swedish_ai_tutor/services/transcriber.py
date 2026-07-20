"""Transcription service — converts audio to Swedish text.

Uses OpenAI Whisper API with a Protocol interface for future swapping
to local whisper model.
"""

import logging
from pathlib import Path
from typing import Protocol

from openai import AsyncOpenAI

from swedish_ai_tutor.models.transcript import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    """Protocol for audio transcription services.

    Implement this to swap in a different transcription backend
    (e.g., local whisper, Azure Speech, etc.).
    """

    async def transcribe(self, audio_path: Path) -> Transcript:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to audio file (MP3, WAV, etc.).

        Returns:
            Transcript with full text and optional segments.
        """
        ...  # pragma: no cover


class WhisperAPITranscriber:
    """Transcribes audio using OpenAI Whisper API.

    Produces Swedish text with word-level timestamps where available.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        language: str = "sv",
        client: AsyncOpenAI | None = None,
    ) -> None:
        """Initialize the Whisper transcriber.

        Args:
            api_key: OpenAI API key.
            model: Whisper model name.
            language: ISO language code for transcription.
            client: Optional pre-configured OpenAI client (for testing).
        """
        self._model = model
        self._language = language
        self._client = client or AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio_path: Path) -> Transcript:
        """Transcribe an audio file using Whisper API.

        Args:
            audio_path: Path to audio file.

        Returns:
            Transcript with full text and timed segments.

        Raises:
            FileNotFoundError: If audio file doesn't exist.
            openai.APIError: If Whisper API call fails.
        """
        if not audio_path.exists():
            msg = f"Audio file not found: {audio_path}"
            raise FileNotFoundError(msg)

        logger.info(
            "Transcribing: %s (model=%s, language=%s)",
            audio_path, self._model, self._language,
        )

        with audio_path.open("rb") as audio_file:
            response = await self._client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
                language=self._language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # Parse response — verbose_json includes segments with timestamps
        segments = self._parse_segments(response)
        full_text = response.text if hasattr(response, "text") else str(response)

        logger.info(
            "Transcription complete: %d characters, %d segments",
            len(full_text),
            len(segments),
        )

        return Transcript(
            full_text=full_text,
            segments=segments,
            language=self._language,
        )

    def _parse_segments(self, response: object) -> list[TranscriptSegment]:
        """Parse segments from Whisper verbose_json response.

        Args:
            response: Raw Whisper API response.

        Returns:
            List of transcript segments with timing.
        """
        segments: list[TranscriptSegment] = []

        # The verbose_json response has a `segments` attribute
        raw_segments = getattr(response, "segments", None)
        if not raw_segments:
            return segments

        for seg in raw_segments:
            text = seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")
            start = seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0)
            end = seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0)

            if text.strip():
                segments.append(
                    TranscriptSegment(
                        text=text.strip(),
                        start=float(start),
                        end=float(end),
                    )
                )

        return segments
