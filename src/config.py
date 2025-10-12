# Configuration module
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")
    bot_mode: str = Field(default="polling", description="Bot mode: polling or webhook")

    # Whisper
    whisper_model_size: str = Field(default="base", description="Whisper model size")
    whisper_device: str = Field(default="cpu", description="Device: cpu or cuda")
    whisper_compute_type: str = Field(default="int8", description="Compute type")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db", description="Database URL"
    )

    # Processing
    max_queue_size: int = Field(default=100, description="Maximum queue size")
    max_concurrent_workers: int = Field(default=3, description="Max concurrent workers")
    transcription_timeout: int = Field(default=120, description="Transcription timeout (seconds)")

    # Quotas
    default_daily_quota_seconds: int = Field(
        default=60, description="Default daily quota in seconds"
    )
    max_voice_duration_seconds: int = Field(
        default=300, description="Maximum voice message duration"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
