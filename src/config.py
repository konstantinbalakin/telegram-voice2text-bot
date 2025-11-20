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

    # Queue Configuration
    max_queue_size: int = Field(default=50, description="Maximum queue size")
    max_concurrent_workers: int = Field(default=1, description="Max concurrent transcriptions")
    transcription_timeout: int = Field(default=120, description="Transcription timeout (seconds)")

    # Progress Tracking
    progress_update_interval: int = Field(
        default=5, description="Progress bar update interval (seconds)"
    )
    progress_rtf: float = Field(default=0.3, description="Estimated RTF for progress calculation")

    # Quotas
    default_daily_quota_seconds: int = Field(
        default=60, description="Default daily quota in seconds"
    )
    max_voice_duration_seconds: int = Field(
        default=300, description="Maximum voice message duration (5 minutes)"
    )

    # LLM Refinement Configuration
    llm_refinement_enabled: bool = Field(default=False, description="Enable LLM text refinement")
    llm_provider: str = Field(
        default="deepseek", description="LLM provider: deepseek, openai, gigachat"
    )
    llm_api_key: str | None = Field(default=None, description="LLM API key")
    llm_model: str = Field(default="deepseek-chat", description="LLM model name")
    llm_base_url: str = Field(default="https://api.deepseek.com", description="LLM API base URL")
    llm_refinement_prompt: str = Field(
        default="""Улучши транскрипцию голосового сообщения:
- Исправь орфографические и пунктуационные ошибки
- Добавь правильную пунктуацию и заглавные буквы
- Сохрани исходный смысл и стиль речи
- Верни только исправленный текст без комментариев""",
        description="System prompt for text refinement",
    )
    llm_timeout: int = Field(default=30, description="LLM request timeout in seconds")

    # Hybrid Strategy Configuration
    hybrid_short_threshold: int = Field(
        default=20, description="Duration threshold for hybrid strategy (seconds)"
    )
    hybrid_draft_provider: str = Field(
        default="faster-whisper", description="Provider for draft: faster-whisper, openai"
    )
    hybrid_draft_model: str = Field(
        default="small", description="Model for draft (e.g., tiny, small)"
    )
    hybrid_quality_provider: str = Field(
        default="faster-whisper", description="Provider for quality transcription"
    )
    hybrid_quality_model: str = Field(
        default="medium", description="Model for quality transcription"
    )

    # Audio Preprocessing Configuration
    audio_convert_to_mono: bool = Field(
        default=False, description="Convert audio to mono before transcription"
    )
    audio_target_sample_rate: int = Field(
        default=16000, description="Target sample rate for mono conversion (Hz)"
    )
    audio_speed_multiplier: float = Field(
        default=1.0, description="Audio speed multiplier (0.5-2.0, 1.0=original)"
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
