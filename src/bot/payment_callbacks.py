"""
Payment callback handlers for inline payment buttons.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.services.payments.base import (
    Currency,
    PaymentRequest,
    PaymentType,
    parse_payment_payload,
    period_label,
)
from src.services.subscription_service import PurchasePreview
from src.storage.database import get_session
from src.storage.billing_repositories import MinutePackageRepository, SubscriptionRepository
from src.storage.repositories import UserRepository

if TYPE_CHECKING:
    from src.services.payments.payment_service import PaymentService
    from src.services.subscription_service import SubscriptionService

# Handler type alias
_Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]


logger = logging.getLogger(__name__)


def _fmt_date(dt: Optional[datetime]) -> str:
    """Format datetime as дд.мм.гггг (UTC); SQLite naive datetimes normalized."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y")


def render_purchase_confirmation(
    preview: PurchasePreview,
    tier_name: str,
    tier_limit_minutes: float,
    current_tier_name: str = "",
) -> str:
    """Render confirmation text with dates before payment (#140, волна 5)."""
    if preview.scenario == "renewal":
        return (
            f"📅 Продление подписки {tier_name}\n\n"
            f"Текущая подписка действует до {_fmt_date(preview.started_at)}. "
            f"Новая начнётся {_fmt_date(preview.started_at)} "
            f"и закончится {_fmt_date(preview.expires_at)}.\n\nПродолжить?"
        )
    if preview.scenario == "upgrade":
        return (
            f"⬆️ Апгрейд с {current_tier_name} → {tier_name}: новый лимит действует "
            f"сразу, окончание новой подписки {_fmt_date(preview.expires_at)} "
            f"(включая остаток {preview.carried_days} дн. старой)\n\nПродолжить?"
        )
    # downgrade
    return (
        f"⬇️ С {_fmt_date(preview.started_at)} подписка станет "
        f"{tier_name}: {tier_limit_minutes:.0f} мин/день\n\nПродолжить?"
    )


def _confirm_keyboard(tier_id: int, period: str, provider: str) -> InlineKeyboardMarkup:
    """«Оплатить»/«Отмена» keyboard; Оплатить leads to confirmed payment callback."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Оплатить", callback_data=f"sub_pay_{provider}:{tier_id}:{period}"
                )
            ],
            [InlineKeyboardButton("Отмена", callback_data=f"sub_pay_cancel:{tier_id}:{period}")],
        ]
    )


def _back_button(callback_data: str) -> InlineKeyboardMarkup:
    """Create a single 'Back' button markup."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=callback_data)]])


class PaymentCallbackHandlers:
    """Handlers for payment-related callback queries."""

    def __init__(
        self,
        payment_service: "PaymentService",
        subscription_service: Optional["SubscriptionService"] = None,
    ) -> None:
        self.payment_service = payment_service
        self.subscription_service = subscription_service

    async def _get_db_user_id(self, telegram_user_id: int) -> int:
        """Get internal DB user ID from Telegram user ID.

        Raises:
            ValueError: if user not found
        """
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(telegram_user_id)
            if not db_user:
                raise ValueError(f"User {telegram_user_id} not found in database")
            return db_user.id

    async def _get_package_price(self, package_id: int) -> tuple[int, int]:
        """Get package price (rub kopecks, stars). Raises ValueError if not found."""
        async with get_session() as session:
            repo = MinutePackageRepository(session)
            package = await repo.get_by_id(package_id)
            if not package:
                raise ValueError(f"Package {package_id} not found")
            return package.price_rub, package.price_stars

    async def _get_package_description(self, package_id: int) -> str | None:
        """Get package description from DB."""
        async with get_session() as session:
            repo = MinutePackageRepository(session)
            package = await repo.get_by_id(package_id)
            return package.description if package else None

    async def _get_subscription_price(self, tier_id: int, period: str) -> tuple[int, int]:
        """Get subscription price (rub kopecks, stars) for tier+period. Raises ValueError if not found."""
        async with get_session() as session:
            repo = SubscriptionRepository(session)
            prices = await repo.get_tier_prices(tier_id=tier_id)
            for price in prices:
                if price.period == period:
                    return price.amount_rub, price.amount_stars
            raise ValueError(f"Price not found for tier {tier_id}, period {period}")

    async def _get_subscription_description(self, tier_id: int, period: str) -> str | None:
        """Get subscription description from price or tier."""
        async with get_session() as session:
            repo = SubscriptionRepository(session)
            prices = await repo.get_tier_prices(tier_id=tier_id)
            for price in prices:
                if price.period == period and price.description:
                    return price.description
            tier = await repo.get_tier_by_id(tier_id=tier_id)
            return tier.description if tier else None

    async def _get_tier_name(self, tier_id: int) -> str:
        """Get subscription tier name by ID."""
        async with get_session() as session:
            repo = SubscriptionRepository(session)
            tier = await repo.get_tier_by_id(tier_id=tier_id)
            if not tier:
                return f"Тариф #{tier_id}"
            return tier.name

    async def _get_tier_limit(self, tier_id: int) -> float:
        """Get subscription tier daily limit (minutes) by ID; 0.0 if not found."""
        async with get_session() as session:
            repo = SubscriptionRepository(session)
            tier = await repo.get_tier_by_id(tier_id=tier_id)
            return tier.daily_limit_minutes if tier else 0.0

    async def _get_package_name(self, package_id: int) -> str:
        """Get package display name (e.g. '60 минут')."""
        async with get_session() as session:
            repo = MinutePackageRepository(session)
            package = await repo.get_by_id(package_id)
            if not package:
                return "Пакет минут"
            return package.name

    async def buy_package_stars_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'Buy package with Telegram Stars' callback.

        Callback data format: pkg_stars:{package_id}
        """
        if not update.callback_query or not update.callback_query.data:
            return

        try:
            await update.callback_query.answer()

            data = update.callback_query.data
            parts = data.split(":")
            if len(parts) != 2:
                await update.callback_query.edit_message_text("Ошибка: неверный формат данных")
                return

            package_id = int(parts[1])
            telegram_user_id = update.effective_user.id  # type: ignore[union-attr]
            db_user_id = await self._get_db_user_id(telegram_user_id)
            _, price_stars = await self._get_package_price(package_id)
            pkg_name = await self._get_package_name(package_id)
            pkg_desc = await self._get_package_description(package_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.PACKAGE,
                item_id=package_id,
                amount=price_stars,
                currency=Currency.XTR,
                title=f"Пакет «{pkg_name}»",
                description=pkg_desc or f"Дополнительные {pkg_name} для транскрибации",
                price_label=pkg_name,
            )

            result = await self.payment_service.create_payment(
                provider_name="telegram_stars",
                request=request,
            )

            back = _back_button("billing:packages")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(  # type: ignore[union-attr]
                    f"Для оплаты нажмите на ссылку ниже:\n{result.payment_url}"
                )
            else:
                error_msg = result.error_message or "Неизвестная ошибка"
                await update.callback_query.edit_message_text(
                    f"Ошибка создания платежа: {error_msg}", reply_markup=back
                )
        except ValueError as e:
            logger.error(f"User lookup error in buy_package_stars_callback: {e}")
            await update.callback_query.edit_message_text(
                "Ошибка: пользователь не найден", reply_markup=_back_button("billing:packages")
            )
        except Exception as e:
            logger.error(f"Error in buy_package_stars_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.", reply_markup=_back_button("billing:packages")
            )

    async def _maybe_confirm_subscription_purchase(
        self,
        update: Update,
        db_user_id: int,
        tier_id: int,
        period: str,
        provider: str,
    ) -> bool:
        """Show confirmation before creating payment if user has an active sub (#140).

        Args:
            provider: "stars" | "card" — used in the confirm callback data.

        Returns:
            True — confirmation shown, flow stops here (wait for sub_pay_* callback).
            False — no active subscription, proceed with the normal flow.
        """
        if self.subscription_service is None:
            return False

        preview = await self.subscription_service.preview_purchase(
            user_id=db_user_id, tier_id=tier_id, period=period
        )
        if preview is None:
            return False

        tier_name = await self._get_tier_name(tier_id)
        current_tier = None
        if preview.scenario in ("upgrade", "downgrade"):
            async with get_session() as session:
                repo = SubscriptionRepository(session)
                active = await repo.get_active_subscription(user_id=db_user_id)
                if active:
                    current_tier = await repo.get_tier_by_id(tier_id=active.tier_id)

        text = render_purchase_confirmation(
            preview,
            tier_name=tier_name,
            tier_limit_minutes=await self._get_tier_limit(tier_id),
            current_tier_name=current_tier.name if current_tier else "",
        )
        await update.callback_query.edit_message_text(  # type: ignore[union-attr]
            text,
            reply_markup=_confirm_keyboard(tier_id, period, provider),
        )
        return True

    async def _confirmed_buy_subscription(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        provider: str,
        data: str,
    ) -> None:
        """«Оплатить» confirmed: create payment via the existing path (#140)."""
        parts = data.split(":")
        if len(parts) != 3:
            await update.callback_query.edit_message_text(  # type: ignore[union-attr]
                "Ошибка: неверный формат данных"
            )
            return

        tier_id = int(parts[1])
        period = parts[2]

        if provider == "stars":
            await self._do_buy_subscription(update, tier_id, period, provider_name="telegram_stars")
        else:
            await self._do_buy_subscription(update, tier_id, period, provider_name="yookassa")

    async def _do_buy_subscription(
        self,
        update: Update,
        tier_id: int,
        period: str,
        provider_name: str,
    ) -> None:
        """Create subscription payment and send the payment link (existing flow)."""
        if not update.callback_query:
            return
        try:
            telegram_user_id = update.effective_user.id  # type: ignore[union-attr]
            db_user_id = await self._get_db_user_id(telegram_user_id)

            if provider_name == "telegram_stars":
                price, _ = await self._get_subscription_price(tier_id, period)
                currency = Currency.XTR
            else:
                _, price = await self._get_subscription_price(tier_id, period)
                currency = Currency.RUB

            tier_name = await self._get_tier_name(tier_id)
            period_ru = period_label(period)
            sub_desc = await self._get_subscription_description(tier_id, period)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.SUBSCRIPTION,
                item_id=tier_id,
                amount=price,
                currency=currency,
                title=f"Подписка {tier_name}",
                description=sub_desc or f"Тариф «{tier_name}» — {period_ru.lower()}",
                price_label=f"{tier_name} ({period_ru})",
                period=period,
            )

            result = await self.payment_service.create_payment(
                provider_name=provider_name,
                request=request,
            )

            back = _back_button("billing:subscriptions")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(  # type: ignore[union-attr]
                    f"Для оплаты нажмите на ссылку ниже:\n{result.payment_url}"
                )
            else:
                error_msg = result.error_message or "Неизвестная ошибка"
                await update.callback_query.edit_message_text(
                    f"Ошибка создания платежа: {error_msg}", reply_markup=back
                )
        except ValueError as e:
            logger.error(f"User lookup error in subscription payment: {e}")
            await update.callback_query.edit_message_text(
                "Ошибка: пользователь не найден",
                reply_markup=_back_button("billing:subscriptions"),
            )
        except Exception as e:
            logger.error(f"Error in subscription payment: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.",
                reply_markup=_back_button("billing:subscriptions"),
            )

    async def confirm_subscription_pay_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'Оплатить' confirm button: sub_pay_{provider}:{tier_id}:{period}."""
        if not update.callback_query or not update.callback_query.data:
            return

        await update.callback_query.answer()
        data = update.callback_query.data
        provider = data.split("_", 2)[2].split(":")[0]  # sub_pay_stars -> stars
        await self._confirmed_buy_subscription(update, context, provider, data)

    async def cancel_subscription_pay_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'Отмена' confirm button: sub_pay_cancel:{tier_id}:{period}."""
        if not update.callback_query or not update.callback_query.data:
            return

        await update.callback_query.answer()
        await update.callback_query.edit_message_text(  # type: ignore[union-attr]
            "Отменено",
            reply_markup=_back_button("billing:subscriptions"),
        )

    async def buy_subscription_stars_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'Buy subscription with Telegram Stars' callback.

        Callback data format: sub_stars:{tier_id}:{period}
        """
        if not update.callback_query or not update.callback_query.data:
            return

        try:
            await update.callback_query.answer()

            data = update.callback_query.data
            parts = data.split(":")
            if len(parts) != 3:
                await update.callback_query.edit_message_text("Ошибка: неверный формат данных")
                return

            tier_id = int(parts[1])
            period = parts[2]
            telegram_user_id = update.effective_user.id  # type: ignore[union-attr]
            db_user_id = await self._get_db_user_id(telegram_user_id)

            # UX-подтверждение при живой active-подписке (#140, волна 5)
            if await self._maybe_confirm_subscription_purchase(
                update, db_user_id, tier_id, period, provider="stars"
            ):
                return

            await self._do_buy_subscription(update, tier_id, period, provider_name="telegram_stars")
        except ValueError as e:
            logger.error(f"User lookup error in buy_subscription_stars_callback: {e}")
            await update.callback_query.edit_message_text(
                "Ошибка: пользователь не найден",
                reply_markup=_back_button("billing:subscriptions"),
            )
        except Exception as e:
            logger.error(f"Error in buy_subscription_stars_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.",
                reply_markup=_back_button("billing:subscriptions"),
            )

    async def buy_package_card_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'Buy package with card' callback (YooKassa native Telegram Payments).

        Callback data format: pkg_card:{package_id}
        """
        if not update.callback_query or not update.callback_query.data:
            return

        try:
            await update.callback_query.answer()

            data = update.callback_query.data
            parts = data.split(":")
            if len(parts) != 2:
                await update.callback_query.edit_message_text("Ошибка: неверный формат данных")
                return

            package_id = int(parts[1])
            telegram_user_id = update.effective_user.id  # type: ignore[union-attr]
            db_user_id = await self._get_db_user_id(telegram_user_id)
            price_rub, _ = await self._get_package_price(package_id)
            pkg_name = await self._get_package_name(package_id)
            pkg_desc = await self._get_package_description(package_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.PACKAGE,
                item_id=package_id,
                amount=price_rub,
                currency=Currency.RUB,
                title=f"Пакет «{pkg_name}»",
                description=pkg_desc or f"Дополнительные {pkg_name} для транскрибации",
                price_label=pkg_name,
            )

            result = await self.payment_service.create_payment(
                provider_name="yookassa",
                request=request,
            )

            back = _back_button("billing:packages")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(  # type: ignore[union-attr]
                    f"Для оплаты нажмите на ссылку ниже:\n{result.payment_url}"
                )
            else:
                error_msg = result.error_message or "Неизвестная ошибка"
                await update.callback_query.edit_message_text(
                    f"Ошибка создания платежа: {error_msg}", reply_markup=back
                )
        except ValueError as e:
            logger.error(f"User lookup error in buy_package_card_callback: {e}")
            await update.callback_query.edit_message_text(
                "Ошибка: пользователь не найден", reply_markup=_back_button("billing:packages")
            )
        except Exception as e:
            logger.error(f"Error in buy_package_card_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.", reply_markup=_back_button("billing:packages")
            )

    async def buy_subscription_card_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle 'Buy subscription with card' callback (YooKassa native Telegram Payments).

        Callback data format: sub_card:{tier_id}:{period}
        """
        if not update.callback_query or not update.callback_query.data:
            return

        try:
            await update.callback_query.answer()

            data = update.callback_query.data
            parts = data.split(":")
            if len(parts) != 3:
                await update.callback_query.edit_message_text("Ошибка: неверный формат данных")
                return

            tier_id = int(parts[1])
            period = parts[2]
            telegram_user_id = update.effective_user.id  # type: ignore[union-attr]
            db_user_id = await self._get_db_user_id(telegram_user_id)

            # UX-подтверждение при живой active-подписке (#140, волна 5)
            if await self._maybe_confirm_subscription_purchase(
                update, db_user_id, tier_id, period, provider="card"
            ):
                return

            await self._do_buy_subscription(update, tier_id, period, provider_name="yookassa")
        except ValueError as e:
            logger.error(f"User lookup error in buy_subscription_card_callback: {e}")
            await update.callback_query.edit_message_text(
                "Ошибка: пользователь не найден",
                reply_markup=_back_button("billing:subscriptions"),
            )
        except Exception as e:
            logger.error(f"Error in buy_subscription_card_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.",
                reply_markup=_back_button("billing:subscriptions"),
            )


def pre_checkout_query_handler(payment_service: "PaymentService") -> _Handler:
    """Create a PreCheckoutQuery handler with payload and amount validation."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.pre_checkout_query:
            return

        query = update.pre_checkout_query
        payload_data = parse_payment_payload(query.invoice_payload)

        if not payload_data:
            logger.warning("Pre-checkout: malformed payload %r", query.invoice_payload)
            await query.answer(ok=False, error_message="Невалидный платёж")
            return

        try:
            payment_type = PaymentType(payload_data["payment_type"])
        except ValueError:
            logger.warning("Pre-checkout: unknown payment_type %r", payload_data["payment_type"])
            await query.answer(ok=False, error_message="Невалидный тип платежа")
            return

        item_id = payload_data["item_id"]
        currency = query.currency
        total_amount = query.total_amount

        try:
            async with get_session() as session:
                if payment_type == PaymentType.PACKAGE:
                    repo = MinutePackageRepository(session)
                    package = await repo.get_by_id(item_id)
                    if not package:
                        logger.warning("Pre-checkout: package %d not found", item_id)
                        await query.answer(ok=False, error_message="Товар не найден")
                        return
                    expected = package.price_stars if currency == "XTR" else package.price_rub
                elif payment_type == PaymentType.SUBSCRIPTION:
                    sub_repo = SubscriptionRepository(session)
                    period = payload_data.get("period", "month")
                    prices = await sub_repo.get_tier_prices(tier_id=item_id)
                    matching = [p for p in prices if p.period == period]
                    if not matching:
                        logger.warning(
                            "Pre-checkout: subscription tier %d period %s not found",
                            item_id,
                            period,
                        )
                        await query.answer(ok=False, error_message="Товар не найден")
                        return
                    price = matching[0]
                    expected = price.amount_stars if currency == "XTR" else price.amount_rub
                else:
                    await query.answer(ok=False, error_message="Неизвестный тип платежа")
                    return

            if total_amount != expected:
                logger.warning(
                    "Pre-checkout: amount mismatch for %s:%d — got %d, expected %d",
                    payment_type.value,
                    item_id,
                    total_amount,
                    expected,
                )
                await query.answer(ok=False, error_message="Сумма платежа не совпадает")
                return

            await query.answer(ok=True)
        except Exception as e:
            logger.error("Pre-checkout validation error: %s", e, exc_info=True)
            await query.answer(ok=False, error_message="Ошибка валидации платежа")

    return handler


def successful_payment_handler(payment_service: "PaymentService") -> _Handler:
    """Create a handler for successful Telegram payments (Stars and YooKassa).

    Parses payload, verifies user_id matches effective_user, and calls
    PaymentService.handle_successful_payment(). Detects provider by currency.
    """

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.successful_payment:
            return

        payment = update.message.successful_payment

        try:
            payload_data = parse_payment_payload(payment.invoice_payload)
            if not payload_data:
                logger.error("Failed to parse payment payload: %s", payment.invoice_payload)
                await update.message.reply_text("Ошибка обработки платежа. Свяжитесь с поддержкой.")
                return

            payment_type = PaymentType(payload_data["payment_type"])
            item_id = payload_data["item_id"]
            payload_user_id = payload_data["user_id"]
            period = payload_data.get("period", "month")

            # SECURITY: goods are always credited to the invoice owner
            # (payload_user_id), never to the payer. A Telegram invoice link
            # can be legitimately paid by another account (e.g. a family
            # member without a RU card) — that is not an IDOR attack.
            # See issue #121.
            effective_user = update.effective_user
            payer_db_id: int | None = None
            if effective_user:
                async with get_session() as session:
                    user_repo = UserRepository(session)
                    db_user = await user_repo.get_by_telegram_id(effective_user.id)
                    if db_user:
                        payer_db_id = db_user.id

                if payer_db_id is None:
                    logger.info(
                        "Payment for user %s paid by unregistered tg_id=%s — "
                        "crediting to invoice owner",
                        payload_user_id,
                        effective_user.id,
                    )
                elif payer_db_id != payload_user_id:
                    logger.info(
                        "Payment for user %s paid by another account "
                        "(tg_id=%s, db_id=%s) — crediting to invoice owner",
                        payload_user_id,
                        effective_user.id,
                        payer_db_id,
                    )

            # Detect provider by currency
            provider_name = "yookassa" if payment.currency == "RUB" else "telegram_stars"

            success = await payment_service.handle_successful_payment(
                provider_name=provider_name,
                user_id=payload_user_id,
                payment_type=payment_type,
                item_id=item_id,
                provider_transaction_id=payment.telegram_payment_charge_id,
                period=period,
            )

            if success:
                if payer_db_id is not None and payer_db_id != payload_user_id:
                    # Paid by another account — goods went to the invoice owner
                    await update.message.reply_text(
                        "✅ Платеж успешно обработан!\n"
                        "Минуты зачислены владельцу ссылки на оплату."
                    )
                elif payer_db_id is None:
                    await update.message.reply_text(
                        "✅ Платеж успешно обработан!\n"
                        "Минуты зачислены владельцу ссылки на оплату."
                    )
                else:
                    await update.message.reply_text("✅ Платеж успешно обработан!")
            else:
                await update.message.reply_text("Ошибка обработки платежа. Свяжитесь с поддержкой.")
        except Exception as e:
            logger.error("Error in successful_payment_handler: %s", e, exc_info=True)
            await update.message.reply_text("Ошибка обработки платежа. Попробуйте позже.")

    return handler
