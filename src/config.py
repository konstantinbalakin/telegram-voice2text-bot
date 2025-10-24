# Configuration module
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")
    bot_mode: str = Field(default="polling", description="Bot mode: polling or webhook")

    # Transcription Provider Configuration
    whisper_providers: list[str] = Field(
        default=["faster-whisper"],
        description="Enabled providers: faster-whisper, openai",
    )
    whisper_routing_strategy: str = Field(
        default="single", description="Routing strategy: single, fallback, benchmark"
    )

    # Strategy Configuration
    primary_provider: str = Field(default="faster-whisper", description="Primary provider name")
    fallback_provider: str = Field(default="openai", description="Fallback provider name")
    duration_threshold_seconds: int = Field(
        default=30, description="Duration threshold for routing"
    )

    # FasterWhisper Configuration
    faster_whisper_model_size: str = Field(
        default="medium",
        description="FasterWhisper model size: tiny, base, small, medium, large-v2, large-v3",
    )
    faster_whisper_device: str = Field(default="cpu", description="Device: cpu or cuda")
    faster_whisper_compute_type: str = Field(
        default="int8", description="Compute type: int8, float16, float32"
    )
    faster_whisper_beam_size: int = Field(
        default=1, description="Beam size: 1 (greedy/fastest), 5 (default), 10 (high quality)"
    )
    faster_whisper_vad_filter: bool = Field(
        default=True, description="Enable voice activity detection filter"
    )

    # OpenAI API Configuration
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="whisper-1", description="OpenAI model name")
    openai_timeout: int = Field(default=60, description="OpenAI API timeout in seconds")

    # Benchmark Mode
    benchmark_mode: bool = Field(default=False, description="Enable benchmark mode")
    benchmark_configs: list[dict] = Field(
        default_factory=lambda: [
            # FasterWhisper variants
            # Production default
            {
                "provider_name": "faster-whisper",
                "model_size": "medium",
                "compute_type": "int8",
                "beam_size": 1,
            },
            # OpenAI API (reference)
            # {"provider_name": "openai"}
        ],
        description="Benchmark configurations to test",
    )

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]


# Global settings instance for convenience
# Use get_settings() in tests to allow mocking
settings = get_settings()
