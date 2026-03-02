"""
Billing-related bot commands: /balance, /subscribe, /buy.
Also provides billing-enhanced versions of /start and /help.
"""

import logging
from typing import TYPE_CHECKING

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.services.payments.base import SubscriptionPeriod
from src.storage.database import get_session
from src.storage.repositories import UserRepository

if TYPE_CHECKING:
    from src.services.billing_service import BillingService
    from src.services.subscription_service import SubscriptionService
    from src.services.payments.payment_service import PaymentService

logger = logging.getLogger(__name__)

BILLING_ERROR_MSG = "Произошла ошибка. Попробуйте позже."


class BillingCommands:
    """Billing-related Telegram bot commands."""

    def __init__(
        self,
        billing_service: "BillingService",
        subscription_service: "SubscriptionService",
        payment_service: "PaymentService",
    ) -> None:
        self.billing_service = billing_service
        self.subscription_service = subscription_service
        self.payment_service = payment_service

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /balance command — show user's minute balance and subscription."""
        user = update.effective_user
        if not user or not update.message:
            return

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)
                db_user = await user_repo.get_by_telegram_id(user.id)

            if not db_user:
                await update.message.reply_text("Пользователь не найден. Используйте /start")
                return

            balance = await self.billing_service.get_user_balance(db_user.id)

            lines = [
                "Ваш баланс минут:\n",
                f"Дневной лимит: {balance.daily_limit:.1f} мин",
                f"Использовано сегодня: {balance.daily_used:.1f} мин",
                f"Осталось сегодня: {balance.daily_remaining:.1f} мин",
            ]

            if balance.bonus_minutes > 0:
                lines.append(f"Бонусные минуты: {balance.bonus_minutes:.1f} мин")
            if balance.package_minutes > 0:
                lines.append(f"Пакетные минуты: {balance.package_minutes:.1f} мин")

            lines.append(f"\nВсего доступно: {balance.total_available:.1f} мин")

            # Subscription info
            active_sub = await self.subscription_service.get_active_subscription(db_user.id)
            if active_sub:
                tier = await self.subscription_service.get_tier_by_id(active_sub.tier_id)
                tier_name = tier.name if tier else "Unknown"
                expires = active_sub.expires_at.strftime("%d.%m.%Y")
                renew_status = "автопродление" if active_sub.auto_renew else "без продления"
                lines.append(f"\nПодписка: {tier_name}")
                lines.append(f"Действует до: {expires} ({renew_status})")
            else:
                lines.append("\nПодписка: нет")
                lines.append("Используйте /subscribe для оформления подписки")

            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            logger.error(f"Error in /balance command: {e}", exc_info=True)
            await update.message.reply_text(BILLING_ERROR_MSG)

    async def _build_subscribe_text_and_markup(self) -> tuple[str, InlineKeyboardMarkup | None]:
        """Build subscribe catalog text and button markup."""
        tiers = await self.subscription_service.get_available_tiers()

        if not tiers:
            return "Подписки сейчас недоступны. Попробуйте позже.", None

        lines = ["Доступные подписки:\n"]
        for tier in tiers:
            lines.append(f"--- {tier.name} ---")
            lines.append(f"Дневной лимит: {tier.daily_limit_minutes} мин/день")
            if tier.description:
                lines.append(f"{tier.description}")

        buttons = []
        for tier in tiers:
            prices = await self.subscription_service.get_tier_prices(tier.id)
            if prices:
                for price in prices:
                    period_label = _period_label(price.period)
                    row = []
                    if price.amount_stars:
                        row.append(
                            InlineKeyboardButton(
                                f"{tier.name} ({period_label}) - {price.amount_stars} ⭐",
                                callback_data=f"sub_stars:{tier.id}:{price.period}",
                            )
                        )
                    if price.amount_rub:
                        row.append(
                            InlineKeyboardButton(
                                f"{tier.name} ({period_label}) - {price.amount_rub:.0f} ₽",
                                callback_data=f"sub_card:{tier.id}:{price.period}",
                            )
                        )
                    if row:
                        buttons.append(row)

        if not buttons:
            return "\n".join(lines), None

        text = "\n".join(lines) + "\n\nНажмите на кнопку для оформления подписки:"
        return text, InlineKeyboardMarkup(buttons)

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /subscribe command — show subscription catalog with payment buttons."""
        if not update.message:
            return

        try:
            text, markup = await self._build_subscribe_text_and_markup()
            await update.message.reply_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in /subscribe command: {e}", exc_info=True)
            await update.message.reply_text(BILLING_ERROR_MSG)

    async def back_to_subscribe_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle back:subscribe callback — return to subscription catalog."""
        if not update.callback_query:
            return

        try:
            await update.callback_query.answer()
            text, markup = await self._build_subscribe_text_and_markup()
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in back_to_subscribe_callback: {e}", exc_info=True)

    async def _build_buy_text_and_markup(self) -> tuple[str, InlineKeyboardMarkup | None]:
        """Build buy packages text and button markup."""
        packages = await self.payment_service.get_active_packages()

        if not packages:
            return "Пакеты минут сейчас недоступны. Попробуйте позже.", None

        lines = ["Пакеты минут:\n"]
        for pkg in packages:
            price_parts = []
            if pkg.price_rub:
                price_parts.append(f"{pkg.price_rub:.0f} руб")
            if pkg.price_stars:
                price_parts.append(f"{pkg.price_stars} ⭐")
            lines.append(f"{pkg.name} ({pkg.minutes} мин) — {' / '.join(price_parts)}")

        buttons = []
        for pkg in packages:
            row = []
            if pkg.price_stars:
                row.append(
                    InlineKeyboardButton(
                        f"{pkg.name} ({pkg.price_stars} ⭐)",
                        callback_data=f"pkg_stars:{pkg.id}",
                    )
                )
            if pkg.price_rub:
                row.append(
                    InlineKeyboardButton(
                        f"{pkg.name} ({pkg.price_rub:.0f} ₽)",
                        callback_data=f"pkg_card:{pkg.id}",
                    )
                )
            if row:
                buttons.append(row)

        if not buttons:
            return "\n".join(lines), None

        text = "\n".join(lines) + "\n\nНажмите на кнопку для покупки пакета минут:"
        return text, InlineKeyboardMarkup(buttons)

    async def buy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /buy command — show minute package catalog with payment buttons."""
        if not update.message:
            return

        try:
            text, markup = await self._build_buy_text_and_markup()
            await update.message.reply_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in /buy command: {e}", exc_info=True)
            await update.message.reply_text(BILLING_ERROR_MSG)

    async def back_to_buy_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle back:buy callback — return to packages catalog."""
        if not update.callback_query:
            return

        try:
            await update.callback_query.answer()
            text, markup = await self._build_buy_text_and_markup()
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in back_to_buy_callback: {e}", exc_info=True)

    async def start_command_with_billing(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Enhanced /start with billing info and welcome bonus."""
        user = update.effective_user
        if not user or not update.message:
            return

        try:
            is_new_user = False
            async with get_session() as session:
                user_repo = UserRepository(session)
                db_user = await user_repo.get_by_telegram_id(user.id)
                if not db_user:
                    db_user = await user_repo.create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )
                    is_new_user = True

            # Grant welcome bonus for new users
            if is_new_user and db_user:
                try:
                    await self.billing_service.grant_welcome_bonus(db_user.id)
                except Exception as bonus_err:
                    logger.error(f"Failed to grant welcome bonus: {bonus_err}", exc_info=True)
        except Exception as e:
            logger.error(f"Error in /start billing setup: {e}", exc_info=True)

        welcome_message = (
            "Привет! Я Voice2Text — бот для расшифровки голосовых сообщений.\n\n"
            "Просто пришли аудио, и я:\n"
            "- аккуратно расшифрую текст\n"
            "- расставлю знаки препинания\n"
            "- приведу всё в читабельный вид\n\n"
            "Условия использования:\n"
            "- 10 бесплатных минут в день\n"
            "- 60 бонусных минут в подарок при регистрации\n"
            "- Подписки и пакеты минут: /subscribe, /buy\n\n"
            "Проверить баланс: /balance\n"
            "Помощь: /help"
        )

        await update.message.reply_text(welcome_message)

    async def help_command_with_billing(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Enhanced /help with billing-related commands."""
        if not update.message:
            return

        help_message = (
            "Как пользоваться ботом:\n\n"
            "1. Отправьте голосовое сообщение или аудиофайл\n"
            "2. Дождитесь обработки\n"
            "3. Получите текстовую расшифровку\n\n"
            "Доступные команды:\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n"
            "/stats - Посмотреть статистику\n"
            "/balance - Проверить баланс минут\n"
            "/subscribe - Каталог подписок\n"
            "/buy - Купить пакет минут\n\n"
            "Условия:\n"
            "- 10 бесплатных минут транскрибации в день\n"
            "- Бонусные и пакетные минуты тратятся после дневного лимита\n"
            "- Подписка увеличивает дневной лимит"
        )

        await update.message.reply_text(help_message)


def _period_label(period: str) -> str:
    """Convert period code to human-readable label."""
    labels = {
        SubscriptionPeriod.WEEK: "Неделя",
        SubscriptionPeriod.MONTH: "Месяц",
        SubscriptionPeriod.YEAR: "Год",
    }
    try:
        return labels[SubscriptionPeriod(period)]
    except (ValueError, KeyError):
        return period
