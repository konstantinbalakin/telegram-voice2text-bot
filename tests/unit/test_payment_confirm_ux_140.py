"""#140 волна 5: UX-подтверждение покупки подписки.

- preview_purchase: renewal / upgrade / downgrade / нет-active (интеграционные,
  паттерн test_subscription_purchase_140.py — сервис с готовыми репозиториями
  на async_session).
- render_purchase_confirmation: тексты содержат даты и имена тиров.
- Флоу без active-подписки не показывает подтверждение (мок-тест хендлера).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
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


class TestPreviewRenewal:
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


class TestPreviewUpgrade:
    async def test_higher_tier_returns_upgrade_with_carry(self, async_session, service, tiers):
        user = await _create_user(async_session)
        sub = await service.purchase_subscription(user.id, tiers["basic"].id, "month", PROVIDER)

        preview = await service.preview_purchase(user.id, tiers["pro"].id, "month")

        assert preview is not None
        assert preview.scenario == "upgrade"
        assert preview.tier_id == tiers["pro"].id
        # начинается сразу (сейчас), +30 дней + остаток текущей
        now = datetime.now(timezone.utc)
        assert preview.started_at is not None
        assert abs((preview.started_at - now).total_seconds()) < 60
        expected_remaining = sub.expires_at - now
        assert preview.expires_at is not None
        assert preview.expires_at > now + timedelta(days=29)
        assert preview.expires_at - (now + timedelta(days=30)) == pytest.approx(
            expected_remaining, abs=timedelta(seconds=5)
        )
        assert preview.carried_days >= 29  # месяц вперёд


class TestPreviewDowngrade:
    async def test_lower_tier_returns_downgrade_from_expiry(self, async_session, service, tiers):
        user = await _create_user(async_session)
        sub = await service.purchase_subscription(user.id, tiers["pro"].id, "month", PROVIDER)

        preview = await service.preview_purchase(user.id, tiers["basic"].id, "month")

        assert preview is not None
        assert preview.scenario == "downgrade"
        assert preview.tier_id == tiers["basic"].id
        # смена тира с даты окончания текущей
        assert preview.started_at == sub.expires_at.replace(tzinfo=timezone.utc)
        assert preview.expires_at is None


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


def _preview(scenario: str, started, expires, carried=0):
    from src.services.subscription_service import PurchasePreview

    return PurchasePreview(
        scenario=scenario,
        tier_id=102,
        period="month",
        started_at=started,
        expires_at=expires,
        carried_days=carried,
    )


class TestRenderConfirmation:
    def test_renewal_text_contains_dates(self):
        d1 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        preview = _preview("renewal", d1, d1 + timedelta(days=30))
        text = render_purchase_confirmation(preview, "Pro", 120.0)
        assert "Продление" in text
        assert "15.10.2026" in text
        assert "14.11.2026" in text
        assert "Продолжить" in text

    def test_upgrade_text_contains_tier_names_and_carry(self):
        now = datetime.now(timezone.utc)
        preview = _preview("upgrade", now, now + timedelta(days=45), carried=15)
        text = render_purchase_confirmation(preview, "Pro", 120.0, current_tier_name="Basic")
        assert "Basic" in text
        assert "Pro" in text
        assert "15" in text  # carried days
        assert "Апгрейд" in text or "апгрейд" in text

    def test_downgrade_text_contains_start_date_and_limit(self):
        d1 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        preview = _preview("downgrade", d1, None)
        text = render_purchase_confirmation(preview, "Basic", 30.0)
        assert "15.10.2026" in text
        assert "Basic" in text
        assert "30" in text


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
