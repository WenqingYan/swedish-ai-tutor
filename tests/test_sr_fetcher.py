"""Tests for SR Fetcher service."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from swedish_ai_tutor.services.sr_fetcher import SRFetcher, parse_sr_date

# Sample SR API response
SAMPLE_EPISODES_RESPONSE = {
    "copyright": "Copyright Sveriges Radio 2026. All rights reserved.",
    "episodes": [
        {
            "id": 2838589,
            "title": "Klartext - nyheter på ett enklare sätt",
            "description": "Flera döda efter brand på krog i Thailand.",
            "url": "https://www.sverigesradio.se/avsnitt/2838589",
            "program": {"id": 493, "name": "Klartext"},
            "publishdateutc": "/Date(1783968900000)/",
            "broadcasttime": {
                "starttimeutc": "/Date(1783968900000)/",
                "endtimeutc": "/Date(1783969200000)/",
            },
            "downloadpodfile": {
                "title": "Klartext",
                "description": "",
                "filesizeinbytes": 4810945,
                "program": {"id": 493, "name": "Klartext"},
                "duration": 299,
                "publishdateutc": "/Date(1783968900000)/",
                "id": 10232198,
                "url": "https://static-cdn.sr.se/test/klartext_20260713.mp3",
                "statkey": "/app/avsnitt/klartext",
            },
        },
        {
            "id": 2824624,
            "title": "Klartext - nyheter på ett enklare sätt",
            "description": "Same episode, no audio.",
            "url": "https://www.sverigesradio.se/avsnitt/2824624",
            "program": {"id": 493, "name": "Klartext"},
            "publishdateutc": "/Date(1783961700000)/",
            "broadcasttime": {
                "starttimeutc": "/Date(1783961700000)/",
                "endtimeutc": "/Date(1783962000000)/",
            },
        },
    ],
    "pagination": {"page": 1, "size": 10, "totalhits": 2, "totalpages": 1},
}

EMPTY_RESPONSE = {
    "copyright": "Copyright Sveriges Radio 2026.",
    "episodes": [],
    "pagination": {"page": 1, "size": 0, "totalhits": 0, "totalpages": 0},
}


class TestParseSrDate:
    """Test SR date format parsing."""

    def test_parse_valid_date(self) -> None:
        """Parse a typical SR date string."""
        result = parse_sr_date("/Date(1783968900000)/")
        assert result.year == 2026
        assert result.month == 7
        assert result.day == 13
        assert result.tzinfo == UTC

    def test_parse_invalid_format_raises(self) -> None:
        """Invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse SR date"):
            parse_sr_date("2026-07-13")

    def test_parse_embedded_in_string(self) -> None:
        """Can parse even if embedded in surrounding text."""
        result = parse_sr_date("prefix/Date(1000000000000)/suffix")
        assert result.year == 2001


class TestSRFetcher:
    """Test SR Fetcher with mocked HTTP responses."""

    @respx.mock
    @pytest.mark.asyncio()
    async def test_get_latest_episode_success(self) -> None:
        """Fetches the latest episode with audio."""
        respx.get("https://api.sr.se/api/v2/episodes/index").mock(
            return_value=httpx.Response(200, json=SAMPLE_EPISODES_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            fetcher = SRFetcher(client=client)
            episode = await fetcher.get_latest_episode()

        assert episode is not None
        assert episode.id == 2838589
        assert episode.title == "Klartext - nyheter på ett enklare sätt"
        assert episode.duration_seconds == 299
        assert "klartext_20260713.mp3" in episode.audio_url

    @respx.mock
    @pytest.mark.asyncio()
    async def test_get_latest_episode_no_episodes(self) -> None:
        """Returns None when no episodes found."""
        respx.get("https://api.sr.se/api/v2/episodes/index").mock(
            return_value=httpx.Response(200, json=EMPTY_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            fetcher = SRFetcher(client=client)
            episode = await fetcher.get_latest_episode()

        assert episode is None

    @respx.mock
    @pytest.mark.asyncio()
    async def test_get_latest_episode_with_date(self) -> None:
        """Passes date parameters to the API."""
        route = respx.get("https://api.sr.se/api/v2/episodes/index").mock(
            return_value=httpx.Response(200, json=SAMPLE_EPISODES_RESPONSE)
        )

        target = datetime(2026, 7, 13, tzinfo=UTC)
        async with httpx.AsyncClient() as client:
            fetcher = SRFetcher(client=client)
            await fetcher.get_latest_episode(target_date=target)

        # Verify date params were sent
        request = route.calls[0].request
        assert "fromdate=2026-07-13" in str(request.url)
        assert "todate=2026-07-13" in str(request.url)

    @respx.mock
    @pytest.mark.asyncio()
    async def test_get_latest_episode_skips_no_audio(self) -> None:
        """Skips episodes without audio, returns first with audio."""
        # Reverse order so no-audio episode comes first
        response = {
            **SAMPLE_EPISODES_RESPONSE,
            "episodes": list(reversed(SAMPLE_EPISODES_RESPONSE["episodes"])),
        }
        respx.get("https://api.sr.se/api/v2/episodes/index").mock(
            return_value=httpx.Response(200, json=response)
        )

        async with httpx.AsyncClient() as client:
            fetcher = SRFetcher(client=client)
            episode = await fetcher.get_latest_episode()

        # Should get the one with audio (id 2838589), not the one without
        assert episode is not None
        assert episode.id == 2838589

    @respx.mock
    @pytest.mark.asyncio()
    async def test_download_audio(self, tmp_path: Path) -> None:
        """Downloads audio file to specified directory."""
        from swedish_ai_tutor.models.episode import Episode

        episode = Episode(
            id=2838589,
            title="Test",
            description="Test",
            publish_date=datetime(2026, 7, 13, 18, 55, tzinfo=UTC),
            audio_url="https://static-cdn.sr.se/test/audio.mp3",
            duration_seconds=299,
            url="https://example.com",
        )

        fake_audio = b"\xff\xfb\x90\x00" * 100  # Fake MP3 header bytes
        respx.get("https://static-cdn.sr.se/test/audio.mp3").mock(
            return_value=httpx.Response(200, content=fake_audio)
        )

        async with httpx.AsyncClient() as client:
            fetcher = SRFetcher(client=client)
            path = await fetcher.download_audio(episode, tmp_path / "audio")

        assert path.exists()
        assert path.suffix == ".mp3"
        assert path.read_bytes() == fake_audio
        assert "2026-07-13" in path.name

    @respx.mock
    @pytest.mark.asyncio()
    async def test_download_audio_already_exists(self, tmp_path: Path) -> None:
        """Skips download if file already exists."""
        from swedish_ai_tutor.models.episode import Episode

        episode = Episode(
            id=2838589,
            title="Test",
            description="Test",
            publish_date=datetime(2026, 7, 13, 18, 55, tzinfo=UTC),
            audio_url="https://static-cdn.sr.se/test/audio.mp3",
            duration_seconds=299,
            url="https://example.com",
        )

        # Pre-create the file
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        expected_file = audio_dir / f"lattsvenska_{episode.date_str}_{episode.id}.mp3"
        expected_file.write_bytes(b"existing content")

        async with httpx.AsyncClient() as client:
            fetcher = SRFetcher(client=client)
            path = await fetcher.download_audio(episode, audio_dir)

        assert path == expected_file
        assert path.read_bytes() == b"existing content"  # Not overwritten
