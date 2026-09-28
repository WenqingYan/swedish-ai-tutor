"""Transcription service — converts audio to Swedish text.

Uses OpenAI Whisper API with a Protocol interface for future swapping
to local whisper model.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from openai import AsyncOpenAI

from swedish_ai_tutor.models.transcript import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


class IncompleteTranscriptionError(RuntimeError):
    """Raised when a transcription appears to omit a substantial audio region."""


@dataclass(frozen=True)
class TranscriptionQuality:
    """Completeness signals derived from transcript timing and text volume."""

    duration: float
    text_characters: int
    characters_per_second: float
    largest_gap: float
    trailing_gap: float
    reasons: tuple[str, ...]

    @property
    def suspicious(self) -> bool:
        """Return whether the response likely contains a large omission."""
        return bool(self.reasons)


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
        fallback_model: str = "whisper-1",
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
        self._fallback_model = fallback_model
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
            audio_path,
            self._model,
            self._language,
        )

        transcript, quality = await self._transcribe_once(audio_path, self._model)
        if quality.suspicious and self._model == "gpt-4o-transcribe-diarize":
            logger.warning(
                "Diarized transcription appears incomplete (%s); retrying with %s",
                "; ".join(quality.reasons),
                self._fallback_model,
            )
            transcript, quality = await self._transcribe_once(
                audio_path, self._fallback_model
            )

        if quality.suspicious:
            reasons = "; ".join(quality.reasons)
            raise IncompleteTranscriptionError(
                f"Transcription failed completeness checks: {reasons}"
            )
        return transcript

    async def _transcribe_once(
        self, audio_path: Path, model: str
    ) -> tuple[Transcript, TranscriptionQuality]:
        """Make one transcription request and assess its completeness."""
        request: dict[str, Any] = {
            "model": model,
            "language": self._language,
            "temperature": 0,
        }
        if model == "gpt-4o-transcribe-diarize":
            request.update(
                response_format="diarized_json",
                chunking_strategy="auto",
            )
        elif model.startswith("gpt-4o"):
            request.update(
                response_format="json",
                prompt=(
                    "Skriv ut varje talad mening ordagrant på svenska. Ta med "
                    "reporterns frågor, intervjupersonens svar och korta repliker."
                ),
            )
        else:
            request.update(
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                prompt=(
                    "Radio Sweden, lätt svenska, reporter, intervju, fråga, svar, "
                    "programledare, intervjuperson"
                ),
            )

        with audio_path.open("rb") as audio_file:
            response = await self._client.audio.transcriptions.create(
                file=audio_file,
                **request,
            )

        # Parse response — verbose_json includes segments with timestamps
        segments = self._parse_segments(response)
        full_text = response.text if hasattr(response, "text") else str(response)
        response_duration = float(getattr(response, "duration", 0.0) or 0.0)
        quality = assess_transcription(full_text, segments, response_duration)

        logger.info(
            "Transcription complete: %d characters, %d segments",
            len(full_text),
            len(segments),
        )

        transcript = Transcript(
            full_text=full_text,
            segments=segments,
            language=self._language,
        )
        return transcript, quality

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
            speaker = seg.get("speaker") if isinstance(seg, dict) else getattr(seg, "speaker", None)

            if text.strip():
                segments.append(
                    TranscriptSegment(
                        text=text.strip(),
                        start=float(start),
                        end=float(end),
                        speaker=str(speaker) if speaker is not None else None,
                    )
                )

        return segments


def assess_transcription(
    text: str,
    segments: list[TranscriptSegment],
    response_duration: float = 0.0,
) -> TranscriptionQuality:
    """Detect major omissions without rejecting ordinary pauses or intro music."""
    ordered = sorted(segments, key=lambda segment: segment.start)
    segment_end = max((segment.end for segment in ordered), default=0.0)
    duration = max(response_duration, segment_end)
    gaps: list[float] = []
    previous_end = 0.0
    for segment in ordered:
        gaps.append(max(0.0, segment.start - previous_end))
        previous_end = max(previous_end, segment.end)
    largest_gap = max(gaps, default=0.0)
    trailing_gap = max(0.0, duration - segment_end)
    characters = len("".join(text.split()))
    density = characters / duration if duration > 0 else 0.0
    reasons: list[str] = []
    if duration >= 60 and characters < 300:
        reasons.append(f"only {characters} non-space characters for {duration:.0f}s audio")
    if duration >= 120 and density < 4.0:
        reasons.append(f"low speech-text density ({density:.1f} chars/s)")
    if largest_gap > 30:
        reasons.append(f"{largest_gap:.0f}s internal timeline gap")
    if trailing_gap > 30:
        reasons.append(f"{trailing_gap:.0f}s missing at audio end")
    if duration >= 60 and not ordered:
        reasons.append("no timed segments returned")
    return TranscriptionQuality(
        duration=duration,
        text_characters=characters,
        characters_per_second=density,
        largest_gap=largest_gap,
        trailing_gap=trailing_gap,
        reasons=tuple(reasons),
    )
