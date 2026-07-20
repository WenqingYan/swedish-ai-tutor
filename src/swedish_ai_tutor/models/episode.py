"""Data models for SR Klartext episodes."""

from datetime import datetime

from pydantic import BaseModel, Field


class Episode(BaseModel):
    """Metadata for a single SR Klartext episode.

    Represents one broadcast (typically one per weekday).
    """

    id: int = Field(description="SR episode ID")
    title: str = Field(description="Episode title")
    description: str = Field(description="Short description / headline summary")
    publish_date: datetime = Field(description="UTC publication timestamp")
    audio_url: str = Field(description="Direct URL to MP3 audio file")
    duration_seconds: int = Field(description="Audio duration in seconds")
    url: str = Field(description="Web URL for the episode page")

    @property
    def date_str(self) -> str:
        """Format publish date as YYYY-MM-DD for display and page titles."""
        return self.publish_date.strftime("%Y-%m-%d")
