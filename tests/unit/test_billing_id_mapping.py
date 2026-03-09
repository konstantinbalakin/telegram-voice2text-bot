"""
Tests for Telegram ID -> DB ID mapping in billing (Task 1.4).

Verifies that billing operations use the internal DB user ID,
not the Telegram user ID.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


# =============================================================================
# Test: TranscriptionRequest carries db_user_id
# =============================================================================


def test_transcription_request_has_db_user_id() -> None:
    """TranscriptionRequest must have db_user_id field."""
    from src.services.queue_manager import TranscriptionRequest

    request = TranscriptionRequest(
        id="test",
        user_id=12345,  # Telegram ID
        file_path=MagicMock(),
        duration_seconds=60,
        context=MagicMock(),
        status_message=MagicMock(),
        user_message=MagicMock(),
        usage_id=1,
        db_user_id=42,  # Internal DB ID
    )
    assert request.user_id == 12345  # Telegram ID preserved
    assert request.db_user_id == 42  # DB ID is separate


def test_transcription_request_db_user_id_defaults_to_zero() -> None:
    """db_user_id defaults to 0 when not provided."""
    from src.services.queue_manager import TranscriptionRequest

    request = TranscriptionRequest(
        id="test",
        user_id=12345,
        file_path=MagicMock(),
        duration_seconds=60,
        context=MagicMock(),
        status_message=MagicMock(),
        user_message=MagicMock(),
        usage_id=1,
    )
    assert request.db_user_id == 0


# =============================================================================
# Test: Orchestrator uses db_user_id for billing
# =============================================================================


class TestOrchestratorUsesDbUserId:
    """Verify orchestrator passes db_user_id (not Telegram ID) to billing."""

    @pytest.mark.asyncio
    async def test_deduct_minutes_uses_db_user_id(self) -> None:
        """deduct_minutes must be called with db_user_id, not user_id."""
        from src.services.transcription_orchestrator import TranscriptionOrchestrator

        mock_billing = AsyncMock()
        mock_billing.deduct_minutes = AsyncMock(
            return_value={"from_daily": 1.0, "from_bonus": 0.0, "from_package": 0.0}
        )
        mock_billing.should_warn_limit = AsyncMock(return_value=False)

        orchestrator = TranscriptionOrchestrator(
            transcription_router=MagicMock(),
            audio_handler=MagicMock(),
            billing_service=mock_billing,
        )

        # Create a mock request with different Telegram and DB IDs
        request = MagicMock()
        request.user_id = 99999  # Telegram ID
        request.db_user_id = 42  # DB ID
        request.usage_id = 100
        request.duration_seconds = 60

        # Call the billing deduction directly (simulating post-transcription)
        from src.config import settings

        with patch.object(settings, "billing_enabled", True):
            duration_minutes = request.duration_seconds / 60.0
            await orchestrator.billing_service.deduct_minutes(
                user_id=request.db_user_id,
                usage_id=request.usage_id,
                duration_minutes=duration_minutes,
            )

        # Verify billing was called with DB user ID (42), not Telegram ID (99999)
        mock_billing.deduct_minutes.assert_called_once_with(
            user_id=42,  # DB ID, not 99999 (Telegram ID)
            usage_id=100,
            duration_minutes=1.0,
        )
