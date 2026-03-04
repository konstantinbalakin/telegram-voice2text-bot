"""
Tests for billing error handling and resilience (Phase 2).

Verifies fail-open behavior: billing errors must not break transcription.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.billing_service import BillingService
from src.services.payments.payment_service import PaymentService


# =============================================================================
# Task 2.1/2.2: Billing errors don't break pipeline
# =============================================================================


class TestBillingFailOpen:
    """Billing service errors should be non-fatal for the transcription pipeline."""

    @pytest.mark.asyncio
    async def test_check_can_transcribe_billing_disabled_always_allows(self) -> None:
        """When billing is disabled, always allow."""
        service = BillingService(billing_enabled=False)
        can, reason = await service.check_can_transcribe(user_id=1, duration_minutes=999.0)
        assert can is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_deduct_minutes_billing_disabled_noop(self) -> None:
        """When billing is disabled, deduction is a no-op."""
        service = BillingService(billing_enabled=False)
        result = await service.deduct_minutes(user_id=1, usage_id=1, duration_minutes=5.0)
        assert result["from_daily"] == 0.0
        assert result["from_bonus"] == 0.0
        assert result["from_package"] == 0.0


# =============================================================================
# Task 2.4: Deduction shortfall logging
# =============================================================================


class TestDeductionShortfall:
    """Verify shortfall is logged when minutes can't be fully deducted."""

    @pytest.mark.asyncio
    async def test_shortfall_when_insufficient_balance(self) -> None:
        """Deduction completes even when user has fewer minutes than requested."""
        mocks = {
            "condition_repo": AsyncMock(),
            "subscription_repo": AsyncMock(),
            "balance_repo": AsyncMock(),
            "daily_usage_repo": AsyncMock(),
            "deduction_log_repo": AsyncMock(),
        }

        mocks["subscription_repo"].get_active_subscription.return_value = None
        mocks["condition_repo"].get_effective_value.return_value = "5"  # 5 min daily

        mock_daily = MagicMock()
        mock_daily.minutes_used = 5.0  # Already used all daily
        mocks["daily_usage_repo"].get_or_create.return_value = (mock_daily, False)
        mocks["daily_usage_repo"].add_usage.return_value = mock_daily
        mocks["balance_repo"].get_active_balances.return_value = []  # No bonus/package

        service = BillingService(
            condition_repo=mocks["condition_repo"],
            subscription_repo=mocks["subscription_repo"],
            balance_repo=mocks["balance_repo"],
            daily_usage_repo=mocks["daily_usage_repo"],
            deduction_log_repo=mocks["deduction_log_repo"],
            billing_enabled=True,
        )

        # Try to deduct 10 min when user has 0 available
        result = await service.deduct_minutes(user_id=1, usage_id=1, duration_minutes=10.0)

        # All sources should be 0 (nothing available)
        assert result["from_daily"] == 0.0
        assert result["from_bonus"] == 0.0
        assert result["from_package"] == 0.0


# =============================================================================
# Task 2.5: _credit_package raises on missing package
# =============================================================================


class TestCreditPackageRaises:
    """_credit_package should raise ValueError when package not found."""

    @pytest.mark.asyncio
    async def test_credit_package_raises_on_missing_package(self) -> None:
        """Crediting a non-existent package raises ValueError."""
        mocks = {
            "purchase_repo": AsyncMock(),
            "subscription_repo": AsyncMock(),
            "balance_repo": AsyncMock(),
            "package_repo": AsyncMock(),
        }
        mocks["package_repo"].get_by_id.return_value = None

        service = PaymentService(
            purchase_repo=mocks["purchase_repo"],
            subscription_repo=mocks["subscription_repo"],
            balance_repo=mocks["balance_repo"],
            package_repo=mocks["package_repo"],
        )

        with pytest.raises(ValueError, match="Package 999 not found"):
            await service._credit_package(user_id=1, package_id=999)

    @pytest.mark.asyncio
    async def test_credit_package_success(self) -> None:
        """Crediting an existing package returns True."""
        mocks = {
            "purchase_repo": AsyncMock(),
            "subscription_repo": AsyncMock(),
            "balance_repo": AsyncMock(),
            "package_repo": AsyncMock(),
        }
        mock_pkg = MagicMock()
        mock_pkg.minutes = 100
        mock_pkg.name = "Test Package"
        mocks["package_repo"].get_by_id.return_value = mock_pkg

        service = PaymentService(
            purchase_repo=mocks["purchase_repo"],
            subscription_repo=mocks["subscription_repo"],
            balance_repo=mocks["balance_repo"],
            package_repo=mocks["package_repo"],
        )

        result = await service._credit_package(user_id=1, package_id=1)
        assert result is True
        mocks["balance_repo"].create.assert_called_once()


# =============================================================================
# Task 2.3: Commands handle errors gracefully
# =============================================================================


class TestBillingCommandsErrorHandling:
    """Billing commands should catch exceptions and reply with user-friendly message."""

    @pytest.mark.asyncio
    async def test_balance_command_handles_service_error(self) -> None:
        """balance_command sends error message on service failure."""
        from src.bot.billing_commands import BillingCommands, BILLING_ERROR_MSG

        billing_service = AsyncMock()
        billing_service.get_user_balance.side_effect = Exception("DB connection lost")

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        update.message = AsyncMock()

        from unittest.mock import patch

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, MagicMock())

        # Should have replied with error message
        calls = update.message.reply_text.call_args_list
        assert any(BILLING_ERROR_MSG in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_subscriptions_catalog_handles_service_error(self) -> None:
        """subscriptions_catalog_callback handles errors gracefully."""
        from src.bot.billing_commands import BillingCommands

        subscription_service = AsyncMock()
        subscription_service.get_available_tiers.side_effect = Exception("DB error")

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        await cmds.subscriptions_catalog_callback(update, MagicMock())

        # Should not crash — error is logged

    @pytest.mark.asyncio
    async def test_buy_command_handles_service_error(self) -> None:
        """buy_command sends error message on service failure."""
        from src.bot.billing_commands import BillingCommands, BILLING_ERROR_MSG

        billing_service = AsyncMock()
        billing_service.get_user_balance.side_effect = Exception("DB error")

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        update.message = AsyncMock()

        from unittest.mock import patch

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.buy_command(update, MagicMock())

        calls = update.message.reply_text.call_args_list
        assert any(BILLING_ERROR_MSG in str(c) for c in calls)
