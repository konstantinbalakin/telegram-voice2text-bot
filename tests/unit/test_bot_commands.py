"""
Tests for Bot Commands: /balance, /buy (unified screen), catalogs, detail screens, /start and /help
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User as TelegramUser, Message, Chat, InlineKeyboardMarkup

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


def _make_callback_update(data: str, user_id: int = 123) -> tuple:
    """Create a mock Update with callback_query."""
    callback_query = MagicMock()
    callback_query.data = data
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.effective_user = MagicMock(spec=TelegramUser)
    update.effective_user.id = user_id
    return update, callback_query


def _patch_session_and_user(db_user_id: int = 1):
    """Context manager to patch get_session and UserRepository."""
    mock_session = patch("src.bot.billing_commands.get_session")
    mock_user_repo = patch("src.bot.billing_commands.UserRepository")
    return mock_session, mock_user_repo, db_user_id


# =============================================================================
# /balance command tests (unified screen)
# =============================================================================


class TestBalanceCommand:
    """Tests for /balance command — unified balance screen."""

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
        subscription_service.get_active_subscription = AsyncMock(return_value=None)

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
    async def test_balance_has_navigation_buttons(self) -> None:
        """Test /balance shows inline buttons for subscriptions and packages."""
        from src.bot.billing_commands import BillingCommands

        billing_service = AsyncMock()
        billing_service.get_user_balance = AsyncMock(
            return_value=UserBalance(
                daily_limit=10.0,
                daily_used=0.0,
                daily_remaining=10.0,
                bonus_minutes=0.0,
                package_minutes=0.0,
                total_available=10.0,
            )
        )

        subscription_service = AsyncMock()
        subscription_service.get_active_subscription = AsyncMock(return_value=None)

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = _make_update()

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, _make_context())

        call_kwargs = update.message.reply_text.call_args[1]
        markup = call_kwargs.get("reply_markup")
        assert markup is not None
        assert isinstance(markup, InlineKeyboardMarkup)

        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "billing:subscriptions" in all_callbacks
        assert "billing:packages" in all_callbacks

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

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=None)
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, _make_context())

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
        mock_sub.tier_id = 1
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

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.balance_command(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "Pro" in text
        assert "15.03.2026" in text


# =============================================================================
# /buy command tests (alias for /balance)
# =============================================================================


class TestBuyCommand:
    """Tests for /buy command — alias for unified balance screen."""

    @pytest.mark.asyncio
    async def test_buy_is_alias_for_balance(self) -> None:
        """Test /buy shows the same unified screen as /balance."""
        from src.bot.billing_commands import BillingCommands

        billing_service = AsyncMock()
        billing_service.get_user_balance = AsyncMock(
            return_value=UserBalance(
                daily_limit=10.0,
                daily_used=0.0,
                daily_remaining=10.0,
                bonus_minutes=0.0,
                package_minutes=0.0,
                total_available=10.0,
            )
        )

        subscription_service = AsyncMock()
        subscription_service.get_active_subscription = AsyncMock(return_value=None)

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update = _make_update()

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.buy_command(update, _make_context())

        # Should show balance info with navigation buttons
        call_kwargs = update.message.reply_text.call_args[1]
        markup = call_kwargs.get("reply_markup")
        assert markup is not None
        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "billing:subscriptions" in all_callbacks
        assert "billing:packages" in all_callbacks


# =============================================================================
# Subscription catalog callback tests
# =============================================================================


class TestSubscriptionsCatalog:
    """Tests for billing:subscriptions catalog callback."""

    @pytest.mark.asyncio
    async def test_catalog_shows_tiers(self) -> None:
        """Test subscription catalog shows available tiers."""
        from src.bot.billing_commands import BillingCommands

        tier = MagicMock()
        tier.id = 1
        tier.name = "Pro"
        tier.daily_limit_minutes = 30
        tier.description = "Pro subscription"

        price = MagicMock()
        price.period = "month"
        price.amount_rub = 299.0
        price.amount_stars = 150

        subscription_service = AsyncMock()
        subscription_service.get_available_tiers = AsyncMock(return_value=[tier])
        subscription_service.get_tier_prices = AsyncMock(return_value=[price])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update, callback_query = _make_callback_update("billing:subscriptions")
        await cmds.subscriptions_catalog_callback(update, _make_context())

        callback_query.answer.assert_awaited_once()
        callback_query.edit_message_text.assert_awaited_once()
        text = callback_query.edit_message_text.await_args.args[0]
        assert "Pro" in text
        assert "30" in text

        markup = callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert any("billing:sub_detail:1:month" in cb for cb in all_callbacks)
        assert "billing:back_main" in all_callbacks

    @pytest.mark.asyncio
    async def test_catalog_no_tiers(self) -> None:
        """Test subscription catalog when no tiers available."""
        from src.bot.billing_commands import BillingCommands

        subscription_service = AsyncMock()
        subscription_service.get_available_tiers = AsyncMock(return_value=[])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update, callback_query = _make_callback_update("billing:subscriptions")
        await cmds.subscriptions_catalog_callback(update, _make_context())

        text = callback_query.edit_message_text.await_args.args[0]
        assert "недоступн" in text.lower()


# =============================================================================
# Packages catalog callback tests
# =============================================================================


class TestPackagesCatalog:
    """Tests for billing:packages catalog callback."""

    @pytest.mark.asyncio
    async def test_catalog_shows_packages(self) -> None:
        """Test packages catalog shows available packages."""
        from src.bot.billing_commands import BillingCommands

        pkg = MagicMock()
        pkg.id = 1
        pkg.name = "50 минут"
        pkg.minutes = 50
        pkg.price_rub = 149.0
        pkg.price_stars = 75

        payment_service = AsyncMock()
        payment_service.get_active_packages = AsyncMock(return_value=[pkg])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=payment_service,
        )

        update, callback_query = _make_callback_update("billing:packages")
        await cmds.packages_catalog_callback(update, _make_context())

        callback_query.answer.assert_awaited_once()
        text = callback_query.edit_message_text.await_args.args[0]
        assert "50" in text
        assert "149" in text

        markup = callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert any("billing:pkg_detail:1" in cb for cb in all_callbacks)
        assert "billing:back_main" in all_callbacks

    @pytest.mark.asyncio
    async def test_catalog_no_packages(self) -> None:
        """Test packages catalog when no packages available."""
        from src.bot.billing_commands import BillingCommands

        payment_service = AsyncMock()
        payment_service.get_active_packages = AsyncMock(return_value=[])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=payment_service,
        )

        update, callback_query = _make_callback_update("billing:packages")
        await cmds.packages_catalog_callback(update, _make_context())

        text = callback_query.edit_message_text.await_args.args[0]
        assert "недоступн" in text.lower()


# =============================================================================
# Subscription detail screen tests
# =============================================================================


class TestSubscriptionDetail:
    """Tests for billing:sub_detail callback."""

    @pytest.mark.asyncio
    async def test_detail_shows_info_and_payment_buttons(self) -> None:
        """Test subscription detail shows description and payment buttons."""
        from src.bot.billing_commands import BillingCommands

        mock_tier = MagicMock()
        mock_tier.name = "Pro"
        mock_tier.daily_limit_minutes = 30
        mock_tier.description = "Pro plan"

        mock_price = MagicMock()
        mock_price.period = "week"
        mock_price.amount_rub = 99.0
        mock_price.amount_stars = 50
        mock_price.description = "30 мин/день в течение недели"

        subscription_service = AsyncMock()
        subscription_service.get_tier_by_id = AsyncMock(return_value=mock_tier)
        subscription_service.get_tier_prices = AsyncMock(return_value=[mock_price])

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update, callback_query = _make_callback_update("billing:sub_detail:1:week")
        await cmds.subscription_detail_callback(update, _make_context())

        callback_query.answer.assert_awaited_once()
        text = callback_query.edit_message_text.await_args.args[0]
        assert "Pro" in text
        assert "30 мин/день в течение недели" in text

        markup = callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "sub_card:1:week" in all_callbacks
        assert "sub_stars:1:week" in all_callbacks
        assert "billing:subscriptions" in all_callbacks


# =============================================================================
# Package detail screen tests
# =============================================================================


class TestPackageDetail:
    """Tests for billing:pkg_detail callback."""

    @pytest.mark.asyncio
    async def test_detail_shows_info_and_payment_buttons(self) -> None:
        """Test package detail shows description and payment buttons."""
        from src.bot.billing_commands import BillingCommands

        mock_pkg = MagicMock()
        mock_pkg.id = 1
        mock_pkg.name = "50 минут"
        mock_pkg.minutes = 50
        mock_pkg.price_rub = 149.0
        mock_pkg.price_stars = 75
        mock_pkg.description = "50 дополнительных минут транскрибации"

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update, callback_query = _make_callback_update("billing:pkg_detail:1")

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.MinutePackageRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.get_by_id = AsyncMock(return_value=mock_pkg)
                MockRepo.return_value = mock_repo

                await cmds.package_detail_callback(update, _make_context())

        callback_query.answer.assert_awaited_once()
        text = callback_query.edit_message_text.await_args.args[0]
        assert "50 минут" in text
        assert "50 дополнительных минут транскрибации" in text

        markup = callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "pkg_card:1" in all_callbacks
        assert "pkg_stars:1" in all_callbacks
        assert "billing:packages" in all_callbacks


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
        assert "10" in text or "бесплатн" in text.lower()
        assert "60" in text or "бонус" in text.lower()


# =============================================================================
# Updated /help command tests
# =============================================================================


class TestUpdatedHelpCommand:
    """Tests for updated /help with billing info."""

    @pytest.mark.asyncio
    async def test_help_with_billing_shows_commands(self) -> None:
        """Test /help shows billing commands."""
        from src.bot.billing_commands import BillingCommands

        cmds = BillingCommands(
            billing_service=AsyncMock(),
            subscription_service=AsyncMock(),
            payment_service=AsyncMock(),
        )

        update = _make_update()
        await cmds.help_command_with_billing(update, _make_context())

        text = update.message.reply_text.call_args[0][0]
        assert "/balance" in text
        assert "/buy" in text


# =============================================================================
# Back to main callback tests
# =============================================================================


class TestBackToMainCallback:
    """Tests for billing:back_main callback."""

    @pytest.mark.asyncio
    async def test_back_to_main_returns_balance_screen(self) -> None:
        """Test back_to_main edits message with balance screen."""
        from src.bot.billing_commands import BillingCommands

        billing_service = AsyncMock()
        billing_service.get_user_balance = AsyncMock(
            return_value=UserBalance(
                daily_limit=10.0,
                daily_used=0.0,
                daily_remaining=10.0,
                bonus_minutes=0.0,
                package_minutes=0.0,
                total_available=10.0,
            )
        )

        subscription_service = AsyncMock()
        subscription_service.get_active_subscription = AsyncMock(return_value=None)

        cmds = BillingCommands(
            billing_service=billing_service,
            subscription_service=subscription_service,
            payment_service=AsyncMock(),
        )

        update, callback_query = _make_callback_update("billing:back_main")

        with patch("src.bot.billing_commands.get_session") as mock_session:
            mock_sess = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.bot.billing_commands.UserRepository") as MockUserRepo:
                mock_user_repo = AsyncMock()
                mock_user_repo.get_by_telegram_id = AsyncMock(return_value=MagicMock(id=1))
                MockUserRepo.return_value = mock_user_repo

                await cmds.back_to_main_callback(update, _make_context())

        callback_query.answer.assert_awaited_once()
        callback_query.edit_message_text.assert_awaited_once()
        markup = callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        all_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "billing:subscriptions" in all_callbacks
        assert "billing:packages" in all_callbacks
