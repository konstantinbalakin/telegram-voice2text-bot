"""#140 волна 5: UX-подтверждение покупки подписки.

- preview_purchase: renewal / upgrade / downgrade / нет-active (интеграционные,
  паттерн test_subscription_purchase_140.py — сервис с готовыми репозиториями
  на async_session).
- render_purchase_confirmation: тексты содержат даты и имена тиров.
- Флоу без active-подписки не показывает подтверждение (мок-тест хендлера).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from telegram import Update

from src.bot.payment_callbacks import (
    PaymentCallbackHandlers,
    render_purchase_confirmation,
)
from src.services.subscription_service import SubscriptionService
from src.services.payments.base import SubscriptionStatus
from src.storage.models import SubscriptionTier, User, UserSubscription  # noqa: F401

PROVIDER = "test-provider"


# ---------------------------------------------------------------------------
# Integration fixtures (паттерн test_subscription_purchase_140.py)
# ---------------------------------------------------------------------------


async def _create_user(session, telegram_id: int = 42) -> User:
    user = User(telegram_id=telegram_id, username="tester")
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def tiers(async_session):
    from sqlalchemy import insert

    await async_session.execute(
        insert(SubscriptionTier).values(
            id=101, name="Basic", daily_limit_minutes=30.0, display_order=1, is_active=True
        )
    )
    await async_session.execute(
        insert(SubscriptionTier).values(
            id=102, name="Pro", daily_limit_minutes=120.0, display_order=2, is_active=True
        )
    )
    await async_session.flush()
    return {
        "basic": await async_session.get(SubscriptionTier, 101),
        "pro": await async_session.get(SubscriptionTier, 102),
    }


@pytest_asyncio.fixture
def service(async_session):
    from src.storage.billing_repositories import (
        PurchaseRepository,
        SubscriptionRepository,
        UserMinuteBalanceRepository,
    )

    return SubscriptionService(
        subscription_repo=SubscriptionRepository(async_session),
        balance_repo=UserMinuteBalanceRepository(async_session),
        purchase_repo=PurchaseRepository(async_session),
    )


# ---------------------------------------------------------------------------
# preview_purchase
# ---------------------------------------------------------------------------


class TestPreviewAnyTierAtActive:
    """it-007: превью любой покупки при живой active → renewal с датами."""

    async def test_same_tier_returns_renewal_with_dates(self, async_session, service, tiers):
        user = await _create_user(async_session)
        first = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)

        preview = await service.preview_purchase(user.id, tiers["basic"].id, "month")

        assert preview is not None
        assert preview.scenario == "renewal"
        assert preview.tier_id == tiers["basic"].id
        assert preview.started_at == first.expires_at
        assert preview.expires_at == first.expires_at + timedelta(days=30)
        # ничего не записано: строк по-прежнему одна
        from sqlalchemy import select

        rows = (
            (
                await async_session.execute(
                    select(UserSubscription).where(UserSubscription.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    async def test_higher_tier_also_renewal_no_carry(self, async_session, service, tiers):
        user = await _create_user(async_session)
        sub = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)

        preview = await service.preview_purchase(user.id, tiers["pro"].id, "month")

        assert preview is not None
        assert preview.scenario == "renewal"
        assert preview.tier_id == tiers["pro"].id
        # старт = конец текущей, ровно оплаченный период (без остатка)
        assert preview.started_at == sub.expires_at.replace(tzinfo=timezone.utc)
        assert preview.expires_at == preview.started_at + timedelta(days=30)

    async def test_lower_tier_also_renewal(self, async_session, service, tiers):
        user = await _create_user(async_session)
        sub = await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)

        preview = await service.preview_purchase(user.id, tiers["basic"].id, "week")

        assert preview is not None
        assert preview.scenario == "renewal"
        assert preview.tier_id == tiers["basic"].id
        assert preview.started_at == sub.expires_at.replace(tzinfo=timezone.utc)
        delta = preview.expires_at - preview.started_at
        assert timedelta(days=6) < delta <= timedelta(days=7, minutes=1)


class TestPreviewNoActive:
    async def test_no_active_returns_none(self, async_session, service, tiers):
        user = await _create_user(async_session)
        preview = await service.preview_purchase(user.id, tiers["basic"].id, "month")
        assert preview is None

    async def test_expired_row_returns_none(self, async_session, service, tiers):
        user = await _create_user(async_session, telegram_id=77)
        async_session.add(
            UserSubscription(
                user_id=user.id,
                tier_id=tiers["basic"].id,
                period="month",
                started_at=datetime.now(timezone.utc) - timedelta(days=40),
                expires_at=datetime.now(timezone.utc) - timedelta(days=10),
                payment_provider=PROVIDER,
                status=SubscriptionStatus.EXPIRED,
            )
        )
        await async_session.flush()

        preview = await service.preview_purchase(user.id, tiers["basic"].id, "month")
        assert preview is None


# ---------------------------------------------------------------------------
# render_purchase_confirmation
# ---------------------------------------------------------------------------


def _preview(started, expires):
    from src.services.subscription_service import PurchasePreview

    return PurchasePreview(
        scenario="renewal",
        tier_id=102,
        period="month",
        started_at=started,
        expires_at=expires,
    )


class TestRenderConfirmation:
    def test_renewal_text_contains_dates(self):
        d1 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        preview = _preview(d1, d1 + timedelta(days=30))
        text = render_purchase_confirmation(preview, "Pro", 120.0, current_tier_name="Basic")
        assert "Pro" in text
        assert "15.10.2026" in text
        assert "14.11.2026" in text
        assert "Продолжить" in text

    def test_any_tier_same_queued_text_no_instant_upgrade(self):
        """it-007: даже апгрейд — текст про очередь, без «действует сразу»."""
        d1 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        preview = _preview(d1, d1 + timedelta(days=30))
        text = render_purchase_confirmation(preview, "Pro", 120.0, current_tier_name="Basic")
        assert "действует сразу" not in text
        assert "Апгрейд" not in text
        assert "остато" not in text  # без «остаток N дн.»

    def test_text_without_current_tier_name(self):
        d1 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        preview = _preview(d1, d1 + timedelta(days=30))
        text = render_purchase_confirmation(preview, "Basic", 30.0)
        assert "15.10.2026" in text
        assert "Basic" in text
        assert "Продолжить" in text


# ---------------------------------------------------------------------------
# Handler flow: no active sub -> no confirmation, straight to payment
# ---------------------------------------------------------------------------


def _make_callback_query(data: str, user_id: int = 12345) -> MagicMock:
    from telegram import User as TgUser

    user = TgUser(id=user_id, is_bot=False, first_name="Test")
    message = MagicMock()
    message.chat_id = 12345
    message.message_id = 100
    message.reply_text = AsyncMock()

    callback_query = MagicMock()
    callback_query.id = "cb1"
    callback_query.data = data
    callback_query.from_user = user
    callback_query.message = message
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    return callback_query


def _make_update(data: str) -> Update:
    return Update(update_id=1, callback_query=_make_callback_query(data))


class TestNoActiveNoConfirmation:
    async def test_fresh_flow_skips_confirmation(self):
        """Без active-подписки подтверждение не показывается — сразу платёж."""
        payment_service = AsyncMock()
        payment_service.create_payment = AsyncMock(
            return_value=MagicMock(success=True, payment_url="https://t.me/pay")
        )
        subscription_service = AsyncMock()
        subscription_service.preview_purchase = AsyncMock(return_value=None)

        handlers = PaymentCallbackHandlers(
            payment_service=payment_service,
            subscription_service=subscription_service,
        )

        with AsyncMock() as get_db_user:
            get_db_user.side_effect = None
            handlers._get_db_user_id = AsyncMock(return_value=1)
            handlers._get_subscription_price = AsyncMock(return_value=(10000, 500))
            handlers._get_tier_name = AsyncMock(return_value="Pro")
            handlers._get_subscription_description = AsyncMock(return_value=None)
            handlers._get_tier_limit = AsyncMock(return_value=120.0)

            update = _make_update("sub_stars:102:month")
            await handlers.buy_subscription_stars_callback(update, context=AsyncMock())

        # подтверждение НЕ показано
        update.callback_query.edit_message_text.assert_not_called()
        # платёж создан сразу (существующий путь)
        payment_service.create_payment.assert_awaited_once()
        # ссылка отправлена
        update.callback_query.message.reply_text.assert_awaited_once()

    async def test_active_sub_shows_confirmation(self):
        """С active-подпиской показывается подтверждение с кнопками."""
        from unittest.mock import patch

        from src.services.subscription_service import PurchasePreview

        preview = PurchasePreview(
            scenario="renewal",
            tier_id=102,
            period="month",
            started_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
            expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        )
        payment_service = AsyncMock()
        subscription_service = AsyncMock()
        subscription_service.preview_purchase = AsyncMock(return_value=preview)

        handlers = PaymentCallbackHandlers(
            payment_service=payment_service,
            subscription_service=subscription_service,
        )
        handlers._get_db_user_id = AsyncMock(return_value=1)
        handlers._get_tier_name = AsyncMock(return_value="Pro")
        handlers._get_tier_limit = AsyncMock(return_value=120.0)

        # it-007: хендлер всегда подтягивает имя текущего тира из БД —
        # get_session мокается (изоляция от окружения).
        mock_repo = MagicMock()
        mock_repo.get_active_subscription = AsyncMock(return_value=None)

        with (
            patch("src.bot.payment_callbacks.get_session") as get_session_ctx,
            patch("src.bot.payment_callbacks.SubscriptionRepository", return_value=mock_repo),
        ):
            get_session_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            get_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            update = _make_update("sub_stars:102:month")
            await handlers.buy_subscription_stars_callback(update, context=AsyncMock())

        # подтверждение показано через edit_message_text
        update.callback_query.edit_message_text.assert_awaited_once()
        args = update.callback_query.edit_message_text.await_args.args
        kwargs = update.callback_query.edit_message_text.await_args.kwargs
        text = args[0] if args else kwargs.get("text", "")
        assert "01.11.2026" in text
        assert "Продолжить" in text
        # кнопки Оплатить/Отмена
        buttons = [btn.text for row in kwargs["reply_markup"].inline_keyboard for btn in row]
        assert "Оплатить" in buttons
        assert "Отмена" in buttons
        # платёж ещё НЕ создан
        payment_service.create_payment.assert_not_awaited()

    async def test_cancel_callback_edits_cancelled(self):
        handlers = PaymentCallbackHandlers(payment_service=AsyncMock())
        update = _make_update("sub_pay_cancel:102:month")
        await handlers.cancel_subscription_pay_callback(update, context=AsyncMock())

        await_args = update.callback_query.edit_message_text.await_args
        kwargs = await_args.kwargs
        text = await_args.args[0] if await_args.args else kwargs.get("text", "")
        assert text == "Отменено"
        buttons = [btn.text for row in kwargs["reply_markup"].inline_keyboard for btn in row]
        assert buttons == ["« Назад"]

    async def test_confirm_callback_creates_payment(self):
        """«Оплатить» ведёт к фактическому созданию платежа."""
        payment_service = AsyncMock()
        payment_service.create_payment = AsyncMock(
            return_value=MagicMock(success=True, payment_url="https://t.me/pay")
        )
        handlers = PaymentCallbackHandlers(payment_service=payment_service)
        handlers._get_db_user_id = AsyncMock(return_value=1)
        handlers._get_subscription_price = AsyncMock(return_value=(10000, 500))
        handlers._get_tier_name = AsyncMock(return_value="Pro")
        handlers._get_subscription_description = AsyncMock(return_value=None)

        update = _make_update("sub_pay_stars:102:month")
        await handlers.confirm_subscription_pay_callback(update, context=AsyncMock())

        payment_service.create_payment.assert_awaited_once()
        call = payment_service.create_payment.await_args
        assert call.kwargs["provider_name"] == "telegram_stars"
        assert call.kwargs["request"].item_id == 102
        assert call.kwargs["request"].period == "month"
