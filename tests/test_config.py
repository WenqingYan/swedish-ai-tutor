"""Tests for configuration module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from swedish_ai_tutor.config import Settings, get_settings

REQUIRED_ENV = {
    "OPENAI_API_KEY": "sk-test-key-123",
    "NOTION_API_KEY": "secret_test-notion-key",
    "NOTION_PARENT_PAGE_ID": "abc123def456",
}


class TestSettings:
    """Test Settings loading and validation."""

    def test_loads_from_env_vars(self) -> None:
        """Settings load successfully with required env vars set."""
        with patch.dict(os.environ, REQUIRED_ENV, clear=False):
            settings = Settings()  # type: ignore[call-arg]

        assert settings.openai_api_key == "sk-test-key-123"
        assert settings.notion_api_key == "secret_test-notion-key"
        assert settings.notion_parent_page_id == "abc123def456"

    def test_defaults_are_correct(self) -> None:
        """Default values match expected SR API settings."""
        with patch.dict(os.environ, REQUIRED_ENV, clear=False):
            settings = Settings()  # type: ignore[call-arg]

        assert settings.sr_program_id == 4916
        assert settings.sr_api_base == "https://api.sr.se/api/v2"
        # openai_model and whisper_model may be overridden by .env
        assert settings.whisper_model in (
            "whisper-1",
            "gpt-4o-transcribe-diarize",
        )
        assert settings.log_level in ("INFO", "DEBUG")

    def test_missing_required_key_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing required keys raise a clear ValidationError."""
        # Must prevent reading from .env file
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("NOTION_API_KEY", raising=False)
        monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)  # type: ignore[call-arg]

        # Should mention a missing field
        error_text = str(exc_info.value).lower()
        assert "openai_api_key" in error_text or "notion" in error_text

    def test_custom_paths(self) -> None:
        """Custom data_dir and db_path are respected."""
        env = {**REQUIRED_ENV, "DATA_DIR": "/tmp/custom", "DB_PATH": "/tmp/custom/my.db"}
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()  # type: ignore[call-arg]

        assert settings.data_dir == Path("/tmp/custom")
        assert settings.db_path == Path("/tmp/custom/my.db")

    def test_property_paths(self) -> None:
        """Derived path properties are computed from data_dir."""
        with patch.dict(os.environ, REQUIRED_ENV, clear=False):
            settings = Settings()  # type: ignore[call-arg]

        assert settings.audio_dir == Path("./data/audio")
        assert settings.lessons_dir == Path("./data/lessons")
        assert settings.logs_dir == Path("./data/logs")

    def test_ensure_directories_creates_dirs(self, tmp_path: Path) -> None:
        """ensure_directories() creates audio, lessons, and logs dirs."""
        env = {**REQUIRED_ENV, "DATA_DIR": str(tmp_path / "data")}
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()  # type: ignore[call-arg]
            settings.ensure_directories()

        assert (tmp_path / "data" / "audio").is_dir()
        assert (tmp_path / "data" / "lessons").is_dir()
        assert (tmp_path / "data" / "logs").is_dir()


class TestGetSettings:
    """Test the get_settings() factory function."""

    def test_returns_settings_instance(self) -> None:
        """get_settings() returns a valid Settings object."""
        with patch.dict(os.environ, REQUIRED_ENV, clear=False):
            settings = get_settings()

        assert isinstance(settings, Settings)
        assert settings.openai_api_key == "sk-test-key-123"
