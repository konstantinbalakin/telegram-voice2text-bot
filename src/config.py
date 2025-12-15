# Configuration module
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram Bot API
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")
    bot_mode: str = Field(default="polling", description="Bot mode: polling or webhook")

    # Telegram Client API (MTProto) - for large files >20 MB
    telegram_api_id: int | None = Field(
        default=None, description="Telegram API ID from my.telegram.org (required for large files)"
    )
    telegram_api_hash: str | None = Field(
        default=None,
        description="Telegram API hash from my.telegram.org (required for large files)",
    )

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def validate_telegram_api_id(cls, v: Any) -> int | None:
        """Convert empty string to None for telegram_api_id."""
        if v == "" or v is None:
            return None
        return int(v)

    @field_validator("telegram_api_hash", mode="before")
    @classmethod
    def validate_telegram_api_hash(cls, v: Any) -> str | None:
        """Convert empty string to None for telegram_api_hash."""
        if v == "" or v is None:
            return None
        return str(v)

    telethon_session_name: str = Field(
        default="bot_client", description="Telethon session file name"
    )
    telethon_enabled: bool = Field(
        default=False, description="Enable Telethon Client API for files >20 MB"
    )

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
    openai_4o_transcribe_preferred_format: str = Field(
        default="mp3",
        description="Preferred audio format for OpenAI gpt-4o-* models (mp3, wav)",
    )

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
    llm_processing_duration: int = Field(
        default=30, description="Estimated LLM processing duration in seconds (for progress bar)"
    )

    # Quotas
    default_daily_quota_seconds: int = Field(
        default=60, description="Default daily quota in seconds"
    )
    max_voice_duration_seconds: int = Field(
        default=300, description="Maximum voice message duration (5 minutes)"
    )
    max_file_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        description="Maximum file size in bytes (20 MB - Telegram Bot API limit)",
    )

    # LLM Refinement Configuration
    llm_refinement_enabled: bool = Field(default=False, description="Enable LLM text refinement")
    llm_provider: str = Field(
        default="deepseek", description="LLM provider: deepseek, openai, gigachat"
    )
    llm_api_key: str | None = Field(default=None, description="LLM API key")
    llm_model: str = Field(default="deepseek-chat", description="LLM model name")
    llm_base_url: str = Field(default="https://api.deepseek.com", description="LLM API base URL")
    llm_timeout: int = Field(default=30, description="LLM request timeout in seconds")
    llm_debug_mode: bool = Field(
        default=False,
        description="Send draft and refined text comparison in separate message for debugging",
    )

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

    # Interactive Transcription Features (Phase 1-8)
    interactive_mode_enabled: bool = Field(
        default=False, description="Enable interactive transcription mode with inline buttons"
    )
    enable_structured_mode: bool = Field(
        default=False, description="Enable 'Structured' text mode (Phase 2)"
    )
    enable_summary_mode: bool = Field(default=False, description="Enable 'Summary' mode (Phase 4)")
    enable_emoji_option: bool = Field(default=False, description="Enable emoji option (Phase 5)")
    enable_timestamps_option: bool = Field(
        default=False, description="Enable timestamps option (Phase 6)"
    )
    enable_length_variations: bool = Field(
        default=False, description="Enable length variations (shorter/longer) (Phase 3)"
    )
    enable_retranscribe: bool = Field(
        default=False, description="Enable retranscription option (Phase 8)"
    )

    # Interactive Transcription Limits
    max_cached_variants_per_transcription: int = Field(
        default=10, description="Maximum number of cached variants per transcription"
    )
    variant_cache_ttl_days: int = Field(
        default=7, description="Days to keep cached variants before cleanup"
    )
    timestamps_min_duration: int = Field(
        default=300, description="Minimum audio duration (seconds) to save segments for timestamps"
    )

    # Retranscription Configuration (Phase 8)
    persistent_audio_dir: str = Field(
        default="./data/audio_files",
        description="Directory for storing audio files for retranscription",
    )
    persistent_audio_ttl_days: int = Field(
        default=7, description="How long to keep audio files (days)"
    )
    retranscribe_free_model: str = Field(
        default="medium", description="Model for free retranscription (higher quality)"
    )
    retranscribe_free_model_rtf: float = Field(default=0.5, description="RTF 0.5 for medium model")
    retranscribe_paid_provider: str = Field(
        default="openai", description="Provider for paid retranscription"
    )
    retranscribe_paid_cost_per_minute: float = Field(
        default=1.0, description="Estimated cost per minute for paid retranscription (rubles)"
    )

    # File Handling (Phase 7)
    file_threshold_chars: int = Field(
        default=3000, description="Text longer than this is sent as .txt file instead of message"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# OpenAI model format compatibility mapping
# Maps model names to required formats (None means supports all formats including OGA)
OPENAI_FORMAT_REQUIREMENTS: dict[str, list[str] | None] = {
    "gpt-4o-transcribe": ["mp3", "wav"],  # New models require conversion from OGA
    "gpt-4o-mini-transcribe": ["mp3", "wav"],  # New models require conversion from OGA
    "whisper-1": None,  # Legacy model supports OGA natively
}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]


# Global settings instance for convenience
# Use get_settings() in tests to allow mocking
settings = get_settings()
