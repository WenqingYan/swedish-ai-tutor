"""Data models for audio transcription output."""

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """A single segment of a transcription with timing information."""

    text: str = Field(description="Transcribed text for this segment")
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    speaker: str | None = Field(
        default=None, description="Speaker label when diarization is available"
    )


class Transcript(BaseModel):
    """Full transcription of an audio episode.

    Contains the complete text and optionally time-aligned segments.
    """

    full_text: str = Field(description="Complete transcription text")
    segments: list[TranscriptSegment] = Field(
        default_factory=list,
        description="Time-aligned segments (if available from transcription API)",
    )
    language: str = Field(default="sv", description="Detected/specified language code")

    @property
    def sentences(self) -> list[str]:
        """Split full text into sentences for analysis.

        Uses period, question mark, and exclamation mark as delimiters.
        Filters out empty strings and strips whitespace.
        """
        import re

        raw_sentences = re.split(r"(?<=[.!?])\s+", self.full_text)
        return [s.strip() for s in raw_sentences if s.strip()]
