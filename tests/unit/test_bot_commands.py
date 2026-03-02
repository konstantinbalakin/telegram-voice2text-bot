"""
Tests for Bot Commands: /balance, /subscribe, /buy, updated /start and /help (Phase 10)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User as TelegramUser, Message, Chat

from src.services.payments.base import UserBalance


# =============================================================================
# Helper to create mock update
# =============================================================================


def _make_update(user_id: int = 123, username: str = "testuser") -> Update:
    """Create a mock Telegram Update with message."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=TelegramUser)
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.message.chat = MagicMock(spec=Chat)
    update.message.chat.id = user_id
    return update


def _make_context() -> MagicMock:
    """Create a mock context."""
    context = MagicMock()
    context.bot = MagicMock()
    return context


# =============================================================================
# /balance command tests
# =============================================================================


class TestBalanceCommand:
    """Tests for /balance command."""

    @pytest.mark.asyncio
    async def test_balance_shows_daily_limit(self) -> None:
        """Test /balance shows daily remaining, bonus, and package minutes."""
        from src.bot.billing_commands import BillingCommands

        billing_service = AsyncMock()
        billing_service.get_user_balance = AsyncMock(
            return_value=UserBalance(
                daily_limit=10.0,
                daily_used=3.5,
                daily_remaining=6.5,
                bonus_minutes=45.0,
                package_minutes=100.0,
                total_available=151.5,
            )
        )

        subscription_service = AsyncMock()
        subscription_service.subscription_repo = AsyncMock()
        subscription_service.subscription_repo.get_active_subscription = AsyncMock(
            return_value=None
        )

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "6.5" in text  # daily_remaining
        assert "45.0" in text or "45" in text  # bonus
        assert "100" in text  # package

    @pytest.mark.asyncio
    async def test_balance_user_not_found(self) -> None:
        """Test /balance when user not in DB."""
        from src.bot.billing_commands import BillingCommands

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=None)
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "/start" in text

    @pytest.mark.asyncio
    async def test_balance_shows_subscription(self) -> None:
        """Test /balance shows active subscription info."""
        from src.bot.billing_commands import BillingCommands

        billing_service = AsyncMock()
        billing_service.get_user_balance = AsyncMock(
            return_value=UserBalance(
                daily_limit=30.0,
                daily_used=5.0,
                daily_remaining=25.0,
                bonus_minutes=0.0,
                package_minutes=0.0,
                total_available=25.0,
            )
        )

        subscription_service = AsyncMock()
        mock_sub = MagicMock()
        mock_sub.expires_at = MagicMock()
        mock_sub.expires_at.strftime = MagicMock(return_value="15.03.2026")
        mock_sub.auto_renew = True
        subscription_service.get_active_subscription = AsyncMock(return_value=mock_sub)
        mock_tier = MagicMock()
        mock_tier.name = "Pro"
        subscription_service.get_tier_by_id = AsyncMock(return_value=mock_tier)

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "Pro" in text
        assert "15.03.2026" in text


# =============================================================================
# /subscribe command tests
# =============================================================================


class TestSubscribeCommand:
    """Tests for /subscribe command."""

    @pytest.mark.asyncio
    async def test_subscribe_shows_tiers(self) -> None:
        """Test /subscribe shows available subscription tiers."""
        from src.bot.billing_commands import BillingCommands

        tier = MagicMock()
        tier.id = 1
        tier.name = "Pro"
        tier.daily_limit_minutes = 30
        tier.description = "Pro subscription"

        price_week = MagicMock()
        price_week.period = "week"
        price_week.amount_rub = 99.0
        price_week.amount_stars = 50

        price_month = MagicMock()
        price_month.period = "month"
        price_month.amount_rub = 299.0
        price_month.amount_stars = 150

        subscription_service = AsyncMock()
        subscription_service.get_available_tiers = AsyncMock(return_value=[tier])
        subscription_service.get_tier_prices = AsyncMock(return_value=[price_week, price_month])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        await cmds.subscribe_command(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Pro" in text
        assert "30" in text  # daily limit

    @pytest.mark.asyncio
    async def test_subscribe_no_tiers(self) -> None:
        """Test /subscribe when no tiers available."""
        from src.bot.billing_commands import BillingCommands

        subscription_service = AsyncMock()
        subscription_service.get_available_tiers = AsyncMock(return_value=[])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        await cmds.subscribe_command(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "нет" in text.lower() or "недоступн" in text.lower()


# =============================================================================
# /buy command tests
# =============================================================================


class TestBuyCommand:
    """Tests for /buy command."""

    @pytest.mark.asyncio
    async def test_buy_shows_packages(self) -> None:
        """Test /buy shows available minute packages."""
        from src.bot.billing_commands import BillingCommands

        pkg1 = MagicMock()
        pkg1.id = 1
        pkg1.name = "50 минут"
        pkg1.minutes = 50
        pkg1.price_rub = 149.0
        pkg1.price_stars = 75

        pkg2 = MagicMock()
        pkg2.id = 2
        pkg2.name = "100 минут"
        pkg2.minutes = 100
        pkg2.price_rub = 249.0
        pkg2.price_stars = 125

        payment_service = AsyncMock()
        payment_service.get_active_packages = AsyncMock(return_value=[pkg1, pkg2])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=payment_service,
        )

        update = _make_update()
        context = _make_context()

        await cmds.buy_command(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "50" in text
        assert "100" in text
        assert "149" in text or "149.0" in text

    @pytest.mark.asyncio
    async def test_buy_no_packages(self) -> None:
        """Test /buy when no packages available."""
        from src.bot.billing_commands import BillingCommands

        payment_service = AsyncMock()
        payment_service.get_active_packages = AsyncMock(return_value=[])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=payment_service,
        )

        update = _make_update()
        context = _make_context()

        await cmds.buy_command(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "нет" in text.lower() or "недоступн" in text.lower()


# =============================================================================
# Updated /start command tests
# =============================================================================


class TestUpdatedStartCommand:
    """Tests for updated /start with billing info."""

    @pytest.mark.asyncio
    async def test_start_with_billing_enabled(self) -> None:
        """Test /start shows billing conditions when billing enabled."""
        from src.bot.billing_commands import BillingCommands

        billing_service = AsyncMock()
        billing_service.grant_welcome_bonus = AsyncMock(return_value=MagicMock())

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=None)
                mock_user_repo.create = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.start_command_with_billing(update, context)

        billing_service.grant_welcome_bonus.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        # Should mention free minutes and bonus
        assert "10" in text or "бесплатн" in text.lower()
        assert "60" in text or "бонус" in text.lower()


# =============================================================================
# Updated /help command tests
# =============================================================================


class TestUpdatedHelpCommand:
    """Tests for updated /help with billing info."""

    @pytest.mark.asyncio
    async def test_help_with_billing_shows_conditions(self) -> None:
        """Test /help shows financial conditions when billing enabled."""
        from src.bot.billing_commands import BillingCommands

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update = _make_update()
        context = _make_context()

        await cmds.help_command_with_billing(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "/balance" in text
        assert "/subscribe" in text or "/buy" in text
