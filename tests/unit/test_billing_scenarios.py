"""
End-to-end tests for billing system full cycle (Phase 12)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# =============================================================================
# E2E: Audio → Billing Check → Deduction → Notification
# =============================================================================


class TestE2ETranscriptionBillingCycle:
    """End-to-end test: send audio → check limit → deduct → notify."""

    @pytest.mark.asyncio
    async def test_full_transcription_cycle_with_billing(self) -> None:
        """Test the complete cycle: check → transcribe → deduct → warn."""
        from src.services.billing_service import BillingService

        # Setup mocks for all repos
        condition_repo = AsyncMock()
        condition_repo.get_effective_value = AsyncMock(return_value="10")

        subscription_repo = AsyncMock()
        subscription_repo.get_active_subscription = AsyncMock(return_value=None)
        subscription_repo.get_active_subscription_with_tier = AsyncMock(return_value=None)

        balance_repo = AsyncMock()
        balance_repo.get_total_minutes = AsyncMock(return_value=0.0)

        daily_usage_repo = AsyncMock()
        mock_usage = MagicMock()
        mock_usage.minutes_used = 0.0
        daily_usage_repo.get_by_user_and_date = AsyncMock(return_value=mock_usage)
        daily_usage_repo.get_or_create = AsyncMock(return_value=(mock_usage, False))
        daily_usage_repo.add_usage = AsyncMock()

        deduction_log_repo = AsyncMock()
        deduction_log_repo.create = AsyncMock()

        service = BillingService(
            condition_repo=condition_repo,
            subscription_repo=subscription_repo,
            balance_repo=balance_repo,
            daily_usage_repo=daily_usage_repo,
            deduction_log_repo=deduction_log_repo,
            billing_enabled=True,
            warning_threshold=0.8,
        )

        # Step 1: Check can transcribe (5 min audio, 10 min daily limit)
        can_transcribe, msg = await service.check_can_transcribe(user_id=1, duration_minutes=5.0)
        assert can_transcribe is True
        assert msg is None

        # Step 2: Deduct 5 minutes
        result = await service.deduct_minutes(user_id=1, usage_id=100, duration_minutes=5.0)
        assert result["from_daily"] == 5.0

        # Step 3: Check warning threshold (now at 50% = 5/10, below 80%)
        mock_usage.minutes_used = 5.0
        should_warn = await service.should_warn_limit(user_id=1)
        assert should_warn is False

        # Step 4: Deduct 4 more minutes (now at 90% = 9/10, above 80%)
        mock_usage.minutes_used = 5.0
        result2 = await service.deduct_minutes(user_id=1, usage_id=101, duration_minutes=4.0)
        assert result2["from_daily"] == 4.0

        mock_usage.minutes_used = 9.0
        should_warn = await service.should_warn_limit(user_id=1)
        assert should_warn is True

    @pytest.mark.asyncio
    async def test_transcription_blocked_when_over_limit(self) -> None:
        """Test that transcription is blocked when daily limit exceeded and no bonus/package."""
        from src.services.billing_service import BillingService

        condition_repo = AsyncMock()
        condition_repo.get_effective_value = AsyncMock(return_value="10")

        subscription_repo = AsyncMock()
        subscription_repo.get_active_subscription = AsyncMock(return_value=None)
        subscription_repo.get_active_subscription_with_tier = AsyncMock(return_value=None)

        balance_repo = AsyncMock()
        balance_repo.get_total_minutes = AsyncMock(return_value=0.0)

        daily_usage_repo = AsyncMock()
        mock_usage = MagicMock()
        mock_usage.minutes_used = 10.0
        daily_usage_repo.get_by_user_and_date = AsyncMock(return_value=mock_usage)

        service = BillingService(
            condition_repo=condition_repo,
            subscription_repo=subscription_repo,
            balance_repo=balance_repo,
            daily_usage_repo=daily_usage_repo,
            deduction_log_repo=AsyncMock(),
            billing_enabled=True,
        )

        can_transcribe, msg = await service.check_can_transcribe(user_id=1, duration_minutes=2.0)
        assert can_transcribe is False
        assert "Недостаточно" in msg


# =============================================================================
# E2E: Purchase Package → Credit → Use
# =============================================================================


class TestE2EPurchaseCycle:
    """End-to-end test: buy package → credit minutes → use them."""

    @pytest.mark.asyncio
    async def test_purchase_package_and_use(self) -> None:
        """Test purchasing a package and using the minutes."""
        from src.services.payments.payment_service import PaymentService
        from src.services.payments.base import PaymentType

        # Mock repos
        purchase_repo = AsyncMock()
        purchase_repo.create = AsyncMock(return_value=MagicMock(id=1))
        purchase_repo.update_status = AsyncMock()
        purchase_repo.find_by_transaction_id = AsyncMock(return_value=None)
        purchase_repo.find_pending_purchase = AsyncMock(return_value=None)

        subscription_repo = AsyncMock()
        balance_repo = AsyncMock()
        balance_repo.create = AsyncMock(return_value=MagicMock(id=1))

        package_repo = AsyncMock()
        mock_package = MagicMock()
        mock_package.minutes = 50
        mock_package.name = "50 минут"
        package_repo.get_by_id = AsyncMock(return_value=mock_package)

        subscription_service = AsyncMock()

        payment_service = PaymentService(
            purchase_repo=purchase_repo,
            subscription_repo=subscription_repo,
            balance_repo=balance_repo,
            package_repo=package_repo,
            subscription_service=subscription_service,
        )

        # Step 1: Handle successful payment
        result = await payment_service.handle_successful_payment(
            provider_name="telegram_stars",
            user_id=1,
            payment_type=PaymentType.PACKAGE,
            item_id=1,
            provider_transaction_id="tx_123",
        )
        assert result is True

        # Verify package minutes were credited
        balance_repo.create.assert_called_once()
        create_call = balance_repo.create.call_args
        assert create_call[1]["minutes_remaining"] == 50

    @pytest.mark.asyncio
    async def test_purchase_subscription_and_activate(self) -> None:
        """Test purchasing a subscription and activating it."""
        from src.services.payments.payment_service import PaymentService
        from src.services.payments.base import PaymentType

        purchase_repo = AsyncMock()
        purchase_repo.create = AsyncMock(return_value=MagicMock(id=1))
        purchase_repo.update_status = AsyncMock()
        purchase_repo.find_by_transaction_id = AsyncMock(return_value=None)
        purchase_repo.find_pending_purchase = AsyncMock(return_value=None)

        subscription_repo = AsyncMock()
        balance_repo = AsyncMock()
        package_repo = AsyncMock()

        subscription_service = AsyncMock()
        subscription_service.create_subscription = AsyncMock(return_value=MagicMock(id=1))

        payment_service = PaymentService(
            purchase_repo=purchase_repo,
            subscription_repo=subscription_repo,
            balance_repo=balance_repo,
            package_repo=package_repo,
            subscription_service=subscription_service,
        )

        result = await payment_service.handle_successful_payment(
            provider_name="telegram_stars",
            user_id=1,
            payment_type=PaymentType.SUBSCRIPTION,
            item_id=1,
            provider_transaction_id="tx_456",
        )
        assert result is True
        subscription_service.create_subscription.assert_called_once()
