"""Tests for src/config.py — Settings defaults, validators, and env overrides."""

import pytest

from src.config import Settings


@pytest.fixture(autouse=True)
def _no_env_file(tmp_path, monkeypatch):
    """Ensure tests don't pick up .env file from project root."""
    monkeypatch.chdir(tmp_path)


class TestSettingsMinimal:
    """Settings can be created with minimal required env vars."""

    def test_creates_with_only_bot_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
        for key in ["OPENAI_API_KEY", "LLM_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        settings = Settings()
        assert settings.telegram_bot_token == "test-token-123"

    def test_missing_bot_token_raises(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(Exception):
            Settings()


class TestSettingsDefaults:
    """Test default values for Settings fields."""

    @pytest.fixture(autouse=True)
    def _set_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")

    # --- Bot ---
    def test_default_bot_mode(self):
        assert Settings().bot_mode == "polling"

    # --- Telegram Client API ---
    def test_default_telegram_api_id_none(self):
        assert Settings().telegram_api_id is None

    def test_default_telegram_api_hash_none(self):
        assert Settings().telegram_api_hash is None

    def test_default_telethon_session_name(self):
        assert Settings().telethon_session_name == "bot_client"

    def test_default_telethon_enabled(self):
        assert Settings().telethon_enabled is False

    # --- Transcription Provider ---
    def test_default_whisper_providers(self):
        assert Settings().whisper_providers == ["faster-whisper"]

    def test_default_whisper_routing_strategy(self):
        assert Settings().whisper_routing_strategy == "single"

    def test_default_primary_provider(self):
        assert Settings().primary_provider == "faster-whisper"

    def test_default_fallback_provider(self):
        assert Settings().fallback_provider == "openai"

    # --- FasterWhisper ---
    def test_default_faster_whisper_model_size(self):
        assert Settings().faster_whisper_model_size == "medium"

    def test_default_faster_whisper_device(self):
        assert Settings().faster_whisper_device == "cpu"

    def test_default_faster_whisper_compute_type(self):
        assert Settings().faster_whisper_compute_type == "int8"

    def test_default_faster_whisper_beam_size(self):
        assert Settings().faster_whisper_beam_size == 1

    def test_default_faster_whisper_vad_filter(self):
        assert Settings().faster_whisper_vad_filter is True

    # --- OpenAI ---
    def test_default_openai_api_key_none(self):
        assert Settings().openai_api_key is None

    def test_default_openai_model(self):
        assert Settings().openai_model == "whisper-1"

    def test_default_openai_timeout(self):
        assert Settings().openai_timeout == 60

    def test_default_openai_4o_transcribe_preferred_format(self):
        assert Settings().openai_4o_transcribe_preferred_format == "mp3"

    # --- Database ---
    def test_default_database_url(self):
        assert Settings().database_url == "sqlite+aiosqlite:///./data/bot.db"

    # --- Queue ---
    def test_default_max_queue_size(self):
        assert Settings().max_queue_size == 50

    def test_default_max_concurrent_workers(self):
        assert Settings().max_concurrent_workers == 1

    def test_default_transcription_timeout(self):
        assert Settings().transcription_timeout == 120

    # --- Progress ---
    def test_default_progress_update_interval(self):
        assert Settings().progress_update_interval == 10

    def test_default_progress_rtf(self):
        assert Settings().progress_rtf == pytest.approx(0.3)

    # --- Quotas ---
    def test_default_enable_quota_check(self):
        assert Settings().enable_quota_check is False

    def test_default_daily_quota_seconds(self):
        assert Settings().default_daily_quota_seconds == 60

    def test_default_max_voice_duration_seconds(self):
        assert Settings().max_voice_duration_seconds == 300

    def test_default_max_file_size_bytes(self):
        assert Settings().max_file_size_bytes == 20 * 1024 * 1024

    # --- LLM ---
    def test_default_llm_refinement_enabled(self):
        assert Settings().llm_refinement_enabled is False

    def test_default_llm_provider(self):
        assert Settings().llm_provider == "deepseek"

    def test_default_llm_api_key_none(self):
        assert Settings().llm_api_key is None

    def test_default_llm_model(self):
        assert Settings().llm_model == "deepseek-chat"

    def test_default_llm_base_url(self):
        assert Settings().llm_base_url == "https://api.deepseek.com"

    def test_default_llm_timeout(self):
        assert Settings().llm_timeout == 30

    def test_default_llm_max_tokens(self):
        assert Settings().llm_max_tokens == 8192

    def test_default_llm_chunking_threshold(self):
        assert Settings().llm_chunking_threshold is None

    def test_default_llm_debug_mode(self):
        assert Settings().llm_debug_mode is False

    # --- Logging ---
    def test_default_log_level(self):
        assert Settings().log_level == "INFO"

    # --- Interactive ---
    def test_default_interactive_mode_enabled(self):
        assert Settings().interactive_mode_enabled is False

    def test_default_enable_magic_mode(self):
        assert Settings().enable_magic_mode is True

    def test_default_enable_structured_mode(self):
        assert Settings().enable_structured_mode is False

    def test_default_enable_summary_mode(self):
        assert Settings().enable_summary_mode is False

    def test_default_max_cached_variants_per_transcription(self):
        assert Settings().max_cached_variants_per_transcription == 10

    def test_default_variant_cache_ttl_days(self):
        assert Settings().variant_cache_ttl_days == 7

    # --- Audio Preprocessing ---
    def test_default_audio_convert_to_mono(self):
        assert Settings().audio_convert_to_mono is False

    def test_default_audio_target_sample_rate(self):
        assert Settings().audio_target_sample_rate == 16000

    def test_default_audio_speed_multiplier(self):
        assert Settings().audio_speed_multiplier == pytest.approx(1.0)

    # --- Document/Video ---
    def test_default_enable_document_handler(self):
        assert Settings().enable_document_handler is True

    def test_default_enable_video_handler(self):
        assert Settings().enable_video_handler is True

    # --- OpenAI Long Audio ---
    def test_default_openai_gpt4o_max_duration(self):
        assert Settings().openai_gpt4o_max_duration == 420

    def test_default_openai_change_model(self):
        assert Settings().openai_change_model is True

    def test_default_openai_chunking(self):
        assert Settings().openai_chunking is False

    def test_default_openai_chunk_size_seconds(self):
        assert Settings().openai_chunk_size_seconds == 1200

    def test_default_openai_parallel_chunks(self):
        assert Settings().openai_parallel_chunks is True


class TestSettingsValidators:
    """Test field_validator methods."""

    @pytest.fixture(autouse=True)
    def _set_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")

    # --- telegram_api_id ---
    def test_telegram_api_id_empty_string_becomes_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_API_ID", "")
        assert Settings().telegram_api_id is None

    def test_telegram_api_id_numeric_string(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        assert Settings().telegram_api_id == 12345

    def test_telegram_api_id_none_stays_none(self):
        s = Settings()
        assert s.telegram_api_id is None

    # --- telegram_api_hash ---
    def test_telegram_api_hash_empty_string_becomes_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_API_HASH", "")
        assert Settings().telegram_api_hash is None

    def test_telegram_api_hash_value(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_API_HASH", "abc123hash")
        assert Settings().telegram_api_hash == "abc123hash"

    def test_telegram_api_hash_none_stays_none(self):
        s = Settings()
        assert s.telegram_api_hash is None


class TestSettingsEnvOverride:
    """Test that env variables override defaults."""

    @pytest.fixture(autouse=True)
    def _set_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")

    def test_override_max_voice_duration_seconds(self, monkeypatch):
        monkeypatch.setenv("MAX_VOICE_DURATION_SECONDS", "7200")
        assert Settings().max_voice_duration_seconds == 7200

    def test_override_log_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        assert Settings().log_level == "DEBUG"

    def test_override_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")
        assert Settings().database_url == "sqlite+aiosqlite:///./data/test.db"

    def test_override_max_queue_size(self, monkeypatch):
        monkeypatch.setenv("MAX_QUEUE_SIZE", "100")
        assert Settings().max_queue_size == 100

    def test_override_max_concurrent_workers(self, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_WORKERS", "4")
        assert Settings().max_concurrent_workers == 4

    def test_override_openai_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-transcribe")
        assert Settings().openai_model == "gpt-4o-transcribe"

    def test_override_llm_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        assert Settings().llm_provider == "openai"

    def test_override_enable_quota_check(self, monkeypatch):
        monkeypatch.setenv("ENABLE_QUOTA_CHECK", "true")
        assert Settings().enable_quota_check is True

    def test_override_interactive_mode_enabled(self, monkeypatch):
        monkeypatch.setenv("INTERACTIVE_MODE_ENABLED", "true")
        assert Settings().interactive_mode_enabled is True

    def test_override_bot_mode(self, monkeypatch):
        monkeypatch.setenv("BOT_MODE", "webhook")
        assert Settings().bot_mode == "webhook"


class TestSettingsFieldConstraints:
    """Test ge/le constraints on numeric fields."""

    @pytest.fixture(autouse=True)
    def _set_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")

    def test_openai_chunk_size_seconds_min(self, monkeypatch):
        monkeypatch.setenv("OPENAI_CHUNK_SIZE_SECONDS", "4")
        with pytest.raises(Exception):
            Settings()

    def test_openai_chunk_size_seconds_max(self, monkeypatch):
        monkeypatch.setenv("OPENAI_CHUNK_SIZE_SECONDS", "1500")
        with pytest.raises(Exception):
            Settings()

    def test_openai_chunk_size_seconds_valid(self, monkeypatch):
        monkeypatch.setenv("OPENAI_CHUNK_SIZE_SECONDS", "600")
        assert Settings().openai_chunk_size_seconds == 600

    def test_openai_chunk_overlap_seconds_min(self, monkeypatch):
        monkeypatch.setenv("OPENAI_CHUNK_OVERLAP_SECONDS", "-1")
        with pytest.raises(Exception):
            Settings()

    def test_openai_chunk_overlap_seconds_max(self, monkeypatch):
        monkeypatch.setenv("OPENAI_CHUNK_OVERLAP_SECONDS", "15")
        with pytest.raises(Exception):
            Settings()

    def test_structure_draft_threshold_min(self, monkeypatch):
        monkeypatch.setenv("STRUCTURE_DRAFT_THRESHOLD", "-1")
        with pytest.raises(Exception):
            Settings()

    def test_structure_draft_threshold_max(self, monkeypatch):
        monkeypatch.setenv("STRUCTURE_DRAFT_THRESHOLD", "5000")
        with pytest.raises(Exception):
            Settings()

    def test_structure_emoji_level_min(self, monkeypatch):
        monkeypatch.setenv("STRUCTURE_EMOJI_LEVEL", "-1")
        with pytest.raises(Exception):
            Settings()

    def test_structure_emoji_level_max(self, monkeypatch):
        monkeypatch.setenv("STRUCTURE_EMOJI_LEVEL", "5")
        with pytest.raises(Exception):
            Settings()

    def test_openai_max_parallel_chunks_min(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MAX_PARALLEL_CHUNKS", "0")
        with pytest.raises(Exception):
            Settings()

    def test_openai_max_parallel_chunks_max(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MAX_PARALLEL_CHUNKS", "20")
        with pytest.raises(Exception):
            Settings()

    def test_llm_max_parallel_chunks_min(self, monkeypatch):
        monkeypatch.setenv("LLM_MAX_PARALLEL_CHUNKS", "0")
        with pytest.raises(Exception):
            Settings()

    def test_llm_max_parallel_chunks_max(self, monkeypatch):
        monkeypatch.setenv("LLM_MAX_PARALLEL_CHUNKS", "20")
        with pytest.raises(Exception):
            Settings()


class TestSettingsModelConfig:
    """Test model_config behavior."""

    def test_extra_fields_ignored(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("TOTALLY_UNKNOWN_FIELD", "hello")
        # Should not raise — extra="ignore"
        Settings()
