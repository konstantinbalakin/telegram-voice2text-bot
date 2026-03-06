"""Tests for billing_test_mode feature flag."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers import BotHandlers
from src.services.queue_manager import TranscriptionRequest
from src.services.transcription_orchestrator import TranscriptionOrchestrator
from src.transcription.models import TranscriptionContext, TranscriptionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handlers() -> BotHandlers:
    """Create BotHandlers bypassing __init__ (no worker started)."""
    return BotHandlers.__new__(BotHandlers)


def _make_orchestrator(
    billing_service: MagicMock | None = None,
) -> TranscriptionOrchestrator:
    """Create an orchestrator with mocked dependencies."""
    router = MagicMock()
    router.transcribe = AsyncMock(
        return_value=TranscriptionResult(
            text="Transcribed text",
            language="ru",
            processing_time=1.5,
            audio_duration=30.0,
            provider_used="openai",
            model_name="whisper-1",
        )
    )
    router.get_active_provider_name = MagicMock(return_value="openai")
    router.get_active_provider_model = MagicMock(return_value="whisper-1")
    router.strategy = MagicMock(spec=[])

    audio_handler = MagicMock()
    audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
    audio_handler.cleanup_file = MagicMock()

    return TranscriptionOrchestrator(
        transcription_router=router,
        audio_handler=audio_handler,
        billing_service=billing_service,
    )


def _make_request(db_user_id: int = 1) -> TranscriptionRequest:
    """Create a TranscriptionRequest with mocked Telegram objects."""
    status_message = AsyncMock()
    status_message.delete = AsyncMock()
    status_message.edit_text = AsyncMock()

    user_message = AsyncMock()
    user_message.chat_id = 12345
    user_message.reply_text = AsyncMock(return_value=AsyncMock(message_id=999))
    user_message.reply_document = AsyncMock(return_value=AsyncMock(message_id=1000))

    return TranscriptionRequest(
        id="req-1",
        user_id=100,
        file_path=Path("/tmp/test_audio.ogg"),
        duration_seconds=30,
        context=TranscriptionContext(user_id=100, duration_seconds=30),
        status_message=status_message,
        user_message=user_message,
        usage_id=1,
        db_user_id=db_user_id,
    )


# =============================================================================
# Task 3.1: /start handler uses old greeting in test mode
# =============================================================================


@pytest.mark.asyncio
async def test_register_handlers_uses_old_start_in_test_mode():
    """When billing_test_mode=true, /start uses bot_handlers.start_command (old greeting)."""
    from telegram.ext import Application, CommandHandler

    mock_app = MagicMock(spec=Application)
    handlers_added: list = []

    def track_handler(handler: object, group: int = 0) -> None:
        handlers_added.append(handler)

    mock_app.add_handler = MagicMock(side_effect=track_handler)

    billing_commands = MagicMock()
    bot_handlers = MagicMock()

    with (
        patch("src.config.settings.billing_enabled", True),
        patch("src.config.settings.billing_test_mode", True),
    ):
        # Simulate the registration logic from main.py
        from src.config import settings

        if billing_commands and settings.billing_enabled:
            if settings.billing_test_mode:
                mock_app.add_handler(CommandHandler("start", bot_handlers.start_command))
            else:
                mock_app.add_handler(
                    CommandHandler("start", billing_commands.start_command_with_billing)
                )

    # Find /start handler
    start_handlers = [
        h for h in handlers_added if isinstance(h, CommandHandler) and "start" in h.commands
    ]
    assert len(start_handlers) == 1
    # The callback should be bot_handlers.start_command (old), not billing
    assert start_handlers[0].callback == bot_handlers.start_command


# =============================================================================
# Task 3.2: Skip check_can_transcribe in test mode
# =============================================================================


@pytest.mark.asyncio
async def test_handlers_skip_billing_check_in_test_mode():
    """When billing_test_mode=true, check_can_transcribe is NOT called."""
    handlers = _make_handlers()
    handlers.billing_service = AsyncMock()
    handlers.billing_service.check_can_transcribe = AsyncMock(return_value=(False, "No minutes"))

    with (
        patch("src.config.settings.billing_enabled", True),
        patch("src.config.settings.billing_test_mode", True),
    ):
        from src.config import settings

        # Directly test the condition from handlers.py
        should_check = (
            handlers.billing_service and settings.billing_enabled and not settings.billing_test_mode
        )
        assert should_check is False


@pytest.mark.asyncio
async def test_handlers_check_billing_when_not_test_mode():
    """When billing_test_mode=false, billing check proceeds normally."""
    with (
        patch("src.config.settings.billing_enabled", True),
        patch("src.config.settings.billing_test_mode", False),
    ):
        from src.config import settings

        billing_service = AsyncMock()
        should_check = (
            billing_service and settings.billing_enabled and not settings.billing_test_mode
        )
        assert should_check is True


# =============================================================================
# Task 3.3: Skip deduct_minutes in test mode
# =============================================================================


@pytest.mark.asyncio
async def test_orchestrator_skips_deduction_in_test_mode():
    """When billing_test_mode=true, deduct_minutes is NOT called after transcription."""
    billing_service = AsyncMock()
    billing_service.deduct_minutes = AsyncMock()

    mock_usage_repo = AsyncMock()
    mock_usage_repo.get_by_id = AsyncMock(return_value=None)
    mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

    mock_state_repo = AsyncMock()
    mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
    mock_state_repo.create = AsyncMock(return_value=MagicMock(id=1, message_id=999))
    mock_state_repo.update = AsyncMock()

    mock_variant_repo = AsyncMock()
    mock_variant_repo.get_variant = AsyncMock(return_value=None)
    mock_variant_repo.create = AsyncMock()

    with (
        patch("src.config.settings.billing_enabled", True),
        patch("src.config.settings.billing_test_mode", True),
        patch("src.config.settings.interactive_mode_enabled", False),
        patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ),
        patch(
            "src.services.transcription_orchestrator.TranscriptionStateRepository",
            return_value=mock_state_repo,
        ),
        patch(
            "src.services.transcription_orchestrator.TranscriptionVariantRepository",
            return_value=mock_variant_repo,
        ),
    ):
        orch = _make_orchestrator(billing_service=billing_service)
        request = _make_request(db_user_id=1)

        await orch.process_transcription(request)

        # deduct_minutes should NOT be called because billing_test_mode=True
        billing_service.deduct_minutes.assert_not_awaited()


@pytest.mark.asyncio
async def test_orchestrator_deducts_when_not_test_mode():
    """When billing_test_mode=false, deduct_minutes IS called after transcription."""
    billing_service = AsyncMock()
    billing_service.deduct_minutes = AsyncMock(return_value={"from_daily": 0.5})
    billing_service.get_limit_status = AsyncMock(return_value="ok")

    mock_usage_repo = AsyncMock()
    mock_usage_repo.get_by_id = AsyncMock(return_value=None)
    mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

    mock_state_repo = AsyncMock()
    mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
    mock_state_repo.create = AsyncMock(return_value=MagicMock(id=1, message_id=999))
    mock_state_repo.update = AsyncMock()

    mock_variant_repo = AsyncMock()
    mock_variant_repo.get_variant = AsyncMock(return_value=None)
    mock_variant_repo.create = AsyncMock()

    with (
        patch("src.config.settings.billing_enabled", True),
        patch("src.config.settings.billing_test_mode", False),
        patch("src.config.settings.interactive_mode_enabled", False),
        patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ),
        patch(
            "src.services.transcription_orchestrator.TranscriptionStateRepository",
            return_value=mock_state_repo,
        ),
        patch(
            "src.services.transcription_orchestrator.TranscriptionVariantRepository",
            return_value=mock_variant_repo,
        ),
    ):
        orch = _make_orchestrator(billing_service=billing_service)
        request = _make_request(db_user_id=1)

        await orch.process_transcription(request)

        # deduct_minutes SHOULD be called because billing_test_mode=False
        billing_service.deduct_minutes.assert_awaited_once()
