"""SR Klartext episode fetcher service.

Fetches episode metadata and downloads audio from the Sveriges Radio Open API.
API docs: https://sverigesradio.se/api/documentation/v2/index.html
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from swedish_ai_tutor.models.episode import Episode

logger = logging.getLogger(__name__)

# SR API date format: "/Date(1783968900000)/"
_SR_DATE_PATTERN = re.compile(r"/Date\((\d+)\)/")


def parse_sr_date(sr_date_str: str) -> datetime:
    """Parse SR API date format to UTC datetime.

    SR uses the format: /Date(milliseconds_since_epoch)/

    Args:
        sr_date_str: Date string in SR format.

    Returns:
        UTC datetime.

    Raises:
        ValueError: If date string doesn't match expected format.
    """
    match = _SR_DATE_PATTERN.search(sr_date_str)
    if not match:
        msg = f"Cannot parse SR date: {sr_date_str}"
        raise ValueError(msg)
    timestamp_ms = int(match.group(1))
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


def _extract_audio_url(episode_data: dict) -> str | None:  # type: ignore[type-arg]
    """Extract the best audio URL from episode data.

    Prefers downloadpodfile > listenpodfile.

    Args:
        episode_data: Raw episode dict from SR API.

    Returns:
        Audio URL string, or None if no audio available.
    """
    for key in ("downloadpodfile", "listenpodfile"):
        pod = episode_data.get(key)
        if pod and pod.get("url"):
            return str(pod["url"])
    return None


def _extract_duration(episode_data: dict) -> int:  # type: ignore[type-arg]
    """Extract duration in seconds from episode data.

    Args:
        episode_data: Raw episode dict from SR API.

    Returns:
        Duration in seconds, or 0 if not available.
    """
    for key in ("downloadpodfile", "listenpodfile"):
        pod = episode_data.get(key)
        if pod and pod.get("duration"):
            return int(pod["duration"])
    return 0


class SRFetcher:
    """Fetches episodes and audio from Sveriges Radio Open API.

    Targets Radio Sweden på lätt svenska (program ID 4916) — Swedish news
    in simplified language for immigrants, ideal for SFI learners.
    """

    def __init__(
        self,
        program_id: int = 4916,
        api_base: str = "https://api.sr.se/api/v2",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the SR fetcher.

        Args:
            program_id: SR program ID (4916 = Radio Sweden på lätt svenska).
            api_base: Base URL for SR API.
            client: Optional httpx client (for testing/injection).
        """
        self._program_id = program_id
        self._api_base = api_base
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def get_latest_episode(
        self, target_date: datetime | None = None
    ) -> Episode | None:
        """Fetch the most recent episode, optionally for a specific date.

        If target_date is provided, fetches episodes from that date.
        Otherwise fetches the most recent available.

        Args:
            target_date: Optional date to fetch episode for.

        Returns:
            Episode model, or None if no episode found.
        """
        client = await self._get_client()
        params: dict[str, str | int] = {
            "programid": self._program_id,
            "format": "json",
            "size": 10,
        }

        if target_date:
            date_str = target_date.strftime("%Y-%m-%d")
            params["fromdate"] = date_str
            params["todate"] = date_str

        url = f"{self._api_base}/episodes/index"
        logger.info("Fetching episodes from SR API: %s", url)

        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        episodes = data.get("episodes", [])
        if not episodes:
            logger.warning("No episodes found for the requested date.")
            return None

        # Find the first episode with audio available
        for ep_data in episodes:
            audio_url = _extract_audio_url(ep_data)
            if audio_url:
                publish_date = parse_sr_date(ep_data["publishdateutc"])
                return Episode(
                    id=ep_data["id"],
                    title=ep_data["title"],
                    description=ep_data.get("description", ""),
                    publish_date=publish_date,
                    audio_url=audio_url,
                    duration_seconds=_extract_duration(ep_data),
                    url=ep_data.get("url", ""),
                )

        logger.warning("Episodes found but none have audio available.")
        return None

    async def get_yesterday_episode(self) -> Episode | None:
        """Convenience method: fetch yesterday's episode.

        Returns:
            Episode from yesterday, or None if not available.
        """
        yesterday = datetime.now(UTC) - timedelta(days=1)
        return await self.get_latest_episode(target_date=yesterday)

    async def download_audio(self, episode: Episode, output_dir: Path) -> Path:
        """Download the episode audio file.

        Args:
            episode: Episode with audio_url to download.
            output_dir: Directory to save the file in.

        Returns:
            Path to the downloaded audio file.

        Raises:
            httpx.HTTPStatusError: If download fails.
        """
        client = await self._get_client()
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"lattsvenska_{episode.date_str}_{episode.id}.mp3"
        output_path = output_dir / filename

        if output_path.exists():
            logger.info("Audio already downloaded: %s", output_path)
            return output_path

        logger.info("Downloading audio: %s", episode.audio_url)
        response = await client.get(episode.audio_url)
        response.raise_for_status()

        output_path.write_bytes(response.content)
        logger.info("Audio saved: %s (%d bytes)", output_path, len(response.content))
        return output_path

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
