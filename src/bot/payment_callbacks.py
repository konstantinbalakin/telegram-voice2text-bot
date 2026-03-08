"""
Payment callback handlers for inline payment buttons.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.services.payments.base import (
    PaymentRequest,
    PaymentType,
    parse_payment_payload,
    period_label,
)
from src.storage.database import get_session
from src.storage.billing_repositories import MinutePackageRepository, SubscriptionRepository
from src.storage.repositories import UserRepository

if TYPE_CHECKING:
    from src.services.payments.payment_service import PaymentService

# Handler type alias
_Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]


logger = logging.getLogger(__name__)


def _back_button(callback_data: str) -> InlineKeyboardMarkup:
    """Create a single 'Back' button markup."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=callback_data)]])


class PaymentCallbackHandlers:
    """Handlers for payment-related callback queries."""

    def __init__(self, payment_service: "PaymentService") -> None:
        self.payment_service = payment_service

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

    async def _get_package_price(self, package_id: int) -> tuple[float, int]:
        """Get package price (rub, stars). Raises ValueError if not found."""
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

    async def _get_subscription_price(self, tier_id: int, period: str) -> tuple[float, int]:
        """Get subscription price (rub, stars) for tier+period. Raises ValueError if not found."""
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
                currency="XTR",
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
            _, price_stars = await self._get_subscription_price(tier_id, period)
            tier_name = await self._get_tier_name(tier_id)
            period_ru = period_label(period)
            sub_desc = await self._get_subscription_description(tier_id, period)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.SUBSCRIPTION,
                item_id=tier_id,
                amount=price_stars,
                currency="XTR",
                title=f"Подписка {tier_name}",
                description=sub_desc or f"Тариф «{tier_name}» — {period_ru.lower()}",
                price_label=f"{tier_name} ({period_ru})",
                period=period,
            )

            result = await self.payment_service.create_payment(
                provider_name="telegram_stars",
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
            amount_kopecks = int(price_rub * 100)
            pkg_name = await self._get_package_name(package_id)
            pkg_desc = await self._get_package_description(package_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.PACKAGE,
                item_id=package_id,
                amount=amount_kopecks,
                currency="RUB",
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
            price_rub, _ = await self._get_subscription_price(tier_id, period)
            amount_kopecks = int(price_rub * 100)
            tier_name = await self._get_tier_name(tier_id)
            period_ru = period_label(period)
            sub_desc = await self._get_subscription_description(tier_id, period)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.SUBSCRIPTION,
                item_id=tier_id,
                amount=amount_kopecks,
                currency="RUB",
                title=f"Подписка {tier_name}",
                description=sub_desc or f"Тариф «{tier_name}» — {period_ru.lower()}",
                price_label=f"{tier_name} ({period_ru})",
                period=period,
            )

            result = await self.payment_service.create_payment(
                provider_name="yookassa",
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
                    expected = (
                        package.price_stars if currency == "XTR" else int(package.price_rub * 100)
                    )
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
                    expected = (
                        price.amount_stars if currency == "XTR" else int(price.amount_rub * 100)
                    )
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

            # SECURITY: verify effective_user matches payload user_id
            effective_user = update.effective_user
            if effective_user:
                async with get_session() as session:
                    user_repo = UserRepository(session)
                    db_user = await user_repo.get_by_telegram_id(effective_user.id)
                    if not db_user or db_user.id != payload_user_id:
                        logger.critical(
                            "IDOR attempt: effective_user tg_id=%s (db_id=%s) != payload user_id=%s",
                            effective_user.id,
                            db_user.id if db_user else "NOT_FOUND",
                            payload_user_id,
                        )
                        await update.message.reply_text(
                            "Ошибка обработки платежа. Свяжитесь с поддержкой."
                        )
                        return

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
                await update.message.reply_text("✅ Платеж успешно обработан!")
            else:
                await update.message.reply_text("Ошибка обработки платежа. Свяжитесь с поддержкой.")
        except Exception as e:
            logger.error("Error in successful_payment_handler: %s", e, exc_info=True)
            await update.message.reply_text("Ошибка обработки платежа. Попробуйте позже.")

    return handler
