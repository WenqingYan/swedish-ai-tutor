"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Swedish AI Tutor configuration.

    All settings are loaded from environment variables or a `.env` file.
    See `.env.example` for documentation of each variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- SR API ---
    sr_program_id: int = 4916
    sr_api_base: str = "https://api.sr.se/api/v2"

    # --- OpenAI ---
    openai_api_key: str
    openai_model: str = "gpt-4o"
    whisper_model: str = "gpt-4o-transcribe-diarize"
    whisper_fallback_model: str = "whisper-1"

    # --- Notion ---
    notion_api_key: str
    notion_parent_page_id: str

    # --- Local paths ---
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/vocabulary.db")
    log_level: str = "INFO"
    web_secure_cookies: bool = True
    web_base_url: str = ""

    # --- Learning ---
    max_news: int = 0  # 0 = all news stories, N = randomly pick N stories from episode

    @property
    def audio_dir(self) -> Path:
        """Directory for downloaded audio files."""
        return self.data_dir / "audio"

    @property
    def lessons_dir(self) -> Path:
        """Directory for saved lesson JSON (fallback/debug)."""
        return self.data_dir / "lessons"

    @property
    def logs_dir(self) -> Path:
        """Directory for pipeline execution logs."""
        return self.data_dir / "logs"

    def ensure_directories(self) -> None:
        """Create all required data directories if they don't exist."""
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Load and return application settings.

    Raises:
        ValidationError: If required environment variables are missing.
    """
    return Settings()
