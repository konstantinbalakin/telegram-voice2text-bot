"""Tests for AsyncService lifecycle protocol."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.lifecycle import AsyncService


class TestAsyncServiceProtocol:
    """Test that AsyncService is a runtime_checkable Protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """AsyncService should be usable with isinstance checks."""

        class GoodService:
            async def initialize(self) -> None:
                pass

            async def shutdown(self) -> None:
                pass

            def is_initialized(self) -> bool:
                return True

        assert isinstance(GoodService(), AsyncService)

    def test_non_conforming_class_fails_isinstance(self) -> None:
        """A class missing methods should not satisfy the protocol."""

        class BadService:
            async def initialize(self) -> None:
                pass

        assert not isinstance(BadService(), AsyncService)

    def test_missing_is_initialized_fails(self) -> None:
        """A class missing is_initialized should not satisfy the protocol."""

        class MissingCheck:
            async def initialize(self) -> None:
                pass

            async def shutdown(self) -> None:
                pass

        assert not isinstance(MissingCheck(), AsyncService)


class TestTranscriptionProviderProtocol:
    """Test that TranscriptionProvider subclasses satisfy AsyncService."""

    def test_openai_provider_satisfies_protocol(self) -> None:
        """OpenAIProvider should satisfy the AsyncService protocol."""
        with patch("src.transcription.providers.openai_provider.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_model = "whisper-1"
            mock_settings.openai_timeout = 30

            from src.transcription.providers.openai_provider import OpenAIProvider

            provider = OpenAIProvider(api_key="test-key")
            assert isinstance(provider, AsyncService)

    def test_faster_whisper_provider_satisfies_protocol(self) -> None:
        """FastWhisperProvider should satisfy the AsyncService protocol."""
        with (
            patch("src.transcription.providers.faster_whisper_provider.settings") as mock_settings,
            patch("src.transcription.providers.faster_whisper_provider.psutil") as mock_psutil,
        ):
            mock_settings.faster_whisper_model_size = "tiny"
            mock_settings.faster_whisper_device = "cpu"
            mock_settings.faster_whisper_compute_type = "int8"
            mock_settings.faster_whisper_beam_size = 5
            mock_settings.faster_whisper_vad_filter = False

            mock_process = MagicMock()
            mock_psutil.Process.return_value = mock_process

            from src.transcription.providers.faster_whisper_provider import (
                FastWhisperProvider,
            )

            provider = FastWhisperProvider(
                model_size="tiny",
                device="cpu",
                compute_type="int8",
            )
            assert isinstance(provider, AsyncService)


class TestTelegramClientServiceProtocol:
    """Test that TelegramClientService satisfies AsyncService."""

    def test_satisfies_protocol(self) -> None:
        """TelegramClientService should satisfy the AsyncService protocol."""
        with patch("src.services.telegram_client.settings") as mock_settings:
            mock_settings.telegram_api_id = 12345
            mock_settings.telegram_api_hash = "test_hash"
            mock_settings.telethon_session_name = "test_session"

            with patch("src.services.telegram_client.TelegramClient"):
                from src.services.telegram_client import TelegramClientService

                service = TelegramClientService()
                assert isinstance(service, AsyncService)

    def test_is_initialized_returns_started_state(self) -> None:
        """is_initialized should return the _started flag."""
        with patch("src.services.telegram_client.settings") as mock_settings:
            mock_settings.telegram_api_id = 12345
            mock_settings.telegram_api_hash = "test_hash"
            mock_settings.telethon_session_name = "test_session"

            with patch("src.services.telegram_client.TelegramClient"):
                from src.services.telegram_client import TelegramClientService

                service = TelegramClientService()
                assert service.is_initialized() is False

                service._started = True
                assert service.is_initialized() is True


class TestLLMServiceProtocol:
    """Test that LLMService satisfies AsyncService."""

    def test_satisfies_protocol(self) -> None:
        """LLMService should satisfy the AsyncService protocol."""
        from src.services.llm_service import LLMService

        service = LLMService(provider=None, prompt="test")
        assert isinstance(service, AsyncService)

    def test_is_initialized_always_true(self) -> None:
        """is_initialized should always return True for LLMService."""
        from src.services.llm_service import LLMService

        service = LLMService(provider=None, prompt="test")
        assert service.is_initialized() is True

    @pytest.mark.asyncio
    async def test_shutdown_calls_close(self) -> None:
        """shutdown should call close (which closes provider)."""
        from src.services.llm_service import LLMService

        mock_provider = AsyncMock()
        service = LLMService(provider=mock_provider, prompt="test")
        await service.shutdown()
        mock_provider.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self) -> None:
        """initialize should be a no-op."""
        from src.services.llm_service import LLMService

        service = LLMService(provider=None, prompt="test")
        await service.initialize()  # Should not raise


class TestAudioHandlerProtocol:
    """Test that AudioHandler satisfies AsyncService."""

    def test_satisfies_protocol(self) -> None:
        """AudioHandler should satisfy the AsyncService protocol."""
        from src.transcription.audio_handler import AudioHandler

        handler = AudioHandler()
        assert isinstance(handler, AsyncService)

    def test_is_initialized_always_true(self) -> None:
        """is_initialized should always return True for AudioHandler."""
        from src.transcription.audio_handler import AudioHandler

        handler = AudioHandler()
        assert handler.is_initialized() is True

    @pytest.mark.asyncio
    async def test_shutdown_closes_http_client(self) -> None:
        """shutdown should close the HTTP client."""
        from src.transcription.audio_handler import AudioHandler

        handler = AudioHandler()
        handler._http_client = AsyncMock()
        await handler.shutdown()
        handler._http_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_is_noop(self) -> None:
        """initialize should be a no-op."""
        from src.transcription.audio_handler import AudioHandler

        handler = AudioHandler()
        await handler.initialize()  # Should not raise
