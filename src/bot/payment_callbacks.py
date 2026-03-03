"""
Payment callback handlers for inline payment buttons.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.services.payments.base import PaymentRequest, PaymentType
from src.storage.database import get_session
from src.storage.repositories import UserRepository

logger = logging.getLogger(__name__)


def _back_button(callback_data: str) -> InlineKeyboardMarkup:
    """Create a single 'Back' button markup."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=callback_data)]])


class PaymentCallbackHandlers:
    """Handlers for payment-related callback queries."""

    def __init__(self, payment_service):
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
            telegram_user_id = update.effective_user.id
            db_user_id = await self._get_db_user_id(telegram_user_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.PACKAGE,
                item_id=package_id,
                amount=0,
                currency="XTR",
                description="Покупка пакета минут",
            )

            result = await self.payment_service.create_payment(
                provider_name="telegram_stars",
                request=request,
            )

            back = _back_button("back:buy")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(
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
                "Ошибка: пользователь не найден", reply_markup=_back_button("back:buy")
            )
        except Exception as e:
            logger.error(f"Error in buy_package_stars_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.", reply_markup=_back_button("back:buy")
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
            telegram_user_id = update.effective_user.id
            db_user_id = await self._get_db_user_id(telegram_user_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.SUBSCRIPTION,
                item_id=tier_id,
                amount=0,
                currency="XTR",
                description=f"Подписка на {period}",
            )

            result = await self.payment_service.create_payment(
                provider_name="telegram_stars",
                request=request,
            )

            back = _back_button("back:subscribe")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(
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
                reply_markup=_back_button("back:subscribe"),
            )
        except Exception as e:
            logger.error(f"Error in buy_subscription_stars_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.",
                reply_markup=_back_button("back:subscribe"),
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
            telegram_user_id = update.effective_user.id
            db_user_id = await self._get_db_user_id(telegram_user_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.PACKAGE,
                item_id=package_id,
                amount=0,
                currency="RUB",
                description="Покупка пакета минут",
            )

            result = await self.payment_service.create_payment(
                provider_name="yookassa",
                request=request,
            )

            back = _back_button("back:buy")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(
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
                "Ошибка: пользователь не найден", reply_markup=_back_button("back:buy")
            )
        except Exception as e:
            logger.error(f"Error in buy_package_card_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.", reply_markup=_back_button("back:buy")
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
            telegram_user_id = update.effective_user.id
            db_user_id = await self._get_db_user_id(telegram_user_id)

            request = PaymentRequest(
                user_id=db_user_id,
                payment_type=PaymentType.SUBSCRIPTION,
                item_id=tier_id,
                amount=0,
                currency="RUB",
                description=f"Подписка на {period}",
            )

            result = await self.payment_service.create_payment(
                provider_name="yookassa",
                request=request,
            )

            back = _back_button("back:subscribe")
            if result.success and result.payment_url:
                await update.callback_query.message.reply_text(
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
                reply_markup=_back_button("back:subscribe"),
            )
        except Exception as e:
            logger.error(f"Error in buy_subscription_card_callback: {e}", exc_info=True)
            await update.callback_query.edit_message_text(
                "Произошла ошибка. Попробуйте позже.",
                reply_markup=_back_button("back:subscribe"),
            )


def pre_checkout_query_handler(payment_service):
    """Create a PreCheckoutQuery handler for Telegram Stars payments.

    Always approves pre-checkout queries for Telegram Stars.
    """

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.pre_checkout_query:
            return

        await update.pre_checkout_query.answer(ok=True)

    return handler


def successful_payment_handler(payment_service):
    """Create a handler for successful Telegram payments (Stars and YooKassa).

    Parses payload and calls PaymentService.handle_successful_payment().
    Detects provider by currency: XTR = telegram_stars, RUB = yookassa.
    """

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.successful_payment:
            return

        payment = update.successful_payment

        try:
            payload_data = _parse_payment_payload(payment.invoice_payload)
            if not payload_data:
                logger.error(f"Failed to parse payment payload: {payment.invoice_payload}")
                await update.message.reply_text("Ошибка обработки платежа. Свяжитесь с поддержкой.")
                return

            payment_type = PaymentType(payload_data["payment_type"])
            item_id = payload_data["item_id"]
            telegram_user_id = payload_data["user_id"]

            # Detect provider by currency
            provider_name = "yookassa" if payment.currency == "RUB" else "telegram_stars"

            db_user_id = await _get_user_db_id(telegram_user_id)

            success = await payment_service.handle_successful_payment(
                provider_name=provider_name,
                user_id=db_user_id,
                payment_type=payment_type,
                item_id=item_id,
                provider_transaction_id=payment.telegram_payment_charge_id,
            )

            if success:
                await update.message.reply_text("✅ Платеж успешно обработан!")
            else:
                await update.message.reply_text("Ошибка обработки платежа. Свяжитесь с поддержкой.")
        except Exception as e:
            logger.error(f"Error in successful_payment_handler: {e}", exc_info=True)
            await update.message.reply_text("Ошибка обработки платежа. Попробуйте позже.")

    return handler


def _parse_payment_payload(payload: str) -> dict | None:
    """Parse payment payload string into components.

    Payload format: {payment_type}:{item_id}:{user_id}
    Used by both Telegram Stars and YooKassa native payments.
    """
    try:
        parts = payload.split(":")
        if len(parts) != 3:
            logger.warning(f"Malformed payment payload (expected 3 parts): {payload!r}")
            return None
        return {
            "payment_type": parts[0],
            "item_id": int(parts[1]),
            "user_id": int(parts[2]),
        }
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse payment payload {payload!r}: {e}")
        return None


async def _get_user_db_id(telegram_user_id: int) -> int:
    """Get internal DB user ID from Telegram user ID."""
    async with get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(telegram_user_id)
        if not db_user:
            raise ValueError(f"User {telegram_user_id} not found in database")
        return db_user.id
