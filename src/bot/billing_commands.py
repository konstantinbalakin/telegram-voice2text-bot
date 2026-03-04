"""
Billing-related bot commands: /balance, /buy (unified screen).
Also provides billing-enhanced versions of /start and /help.
"""

import logging
from typing import TYPE_CHECKING

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.services.payments.base import SubscriptionPeriod
from src.storage.database import get_session
from src.storage.repositories import UserRepository
from src.storage.billing_repositories import MinutePackageRepository

if TYPE_CHECKING:
    from src.services.billing_service import BillingService
    from src.services.subscription_service import SubscriptionService
    from src.services.payments.payment_service import PaymentService

logger = logging.getLogger(__name__)

BILLING_ERROR_MSG = "Произошла ошибка. Попробуйте позже."

_PERIOD_LABELS = {
    SubscriptionPeriod.WEEK: "Неделя",
    SubscriptionPeriod.MONTH: "Месяц",
    SubscriptionPeriod.YEAR: "Год",
}


def _period_label(period: str) -> str:
    """Convert period code to human-readable label."""
    try:
        return _PERIOD_LABELS[SubscriptionPeriod(period)]
    except (ValueError, KeyError):
        return period


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

    # =========================================================================
    # Unified balance screen (/balance and /buy)
    # =========================================================================

    async def _build_balance_text_and_markup(
        self, telegram_user_id: int
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        """Build unified balance screen text and navigation buttons."""
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(telegram_user_id)

        if not db_user:
            return "Пользователь не найден. Используйте /start", None

        balance = await self.billing_service.get_user_balance(db_user.id)

        lines = [
            "💰 Ваш баланс минут:\n",
            f"📊 Дневной лимит: {balance.daily_limit:.0f} мин",
            f"📈 Использовано сегодня: {balance.daily_used:.1f} мин",
            f"📉 Осталось сегодня: {balance.daily_remaining:.1f} мин",
        ]

        if balance.bonus_minutes > 0:
            lines.append(f"🎁 Бонусные минуты: {balance.bonus_minutes:.1f} мин")
        if balance.package_minutes > 0:
            lines.append(f"📦 Пакетные минуты: {balance.package_minutes:.1f} мин")

        lines.append(f"\n✅ Всего доступно: {balance.total_available:.1f} мин")

        # Subscription info
        active_sub = await self.subscription_service.get_active_subscription(db_user.id)
        if active_sub:
            tier = await self.subscription_service.get_tier_by_id(active_sub.tier_id)
            tier_name = tier.name if tier else "Unknown"
            expires = active_sub.expires_at.strftime("%d.%m.%Y")
            lines.append(f"\n⭐ Подписка: {tier_name}")
            lines.append(f"📅 Действует до: {expires}")
        else:
            lines.append("\n📋 Подписка: нет")

        buttons = [
            [InlineKeyboardButton("🔔 Купить подписку", callback_data="billing:subscriptions")],
            [InlineKeyboardButton("📦 Купить пакеты минут", callback_data="billing:packages")],
        ]

        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /balance command — unified balance screen with navigation buttons."""
        user = update.effective_user
        if not user or not update.message:
            return

        try:
            text, markup = await self._build_balance_text_and_markup(user.id)
            await update.message.reply_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in /balance command: {e}", exc_info=True)
            await update.message.reply_text(BILLING_ERROR_MSG)

    async def buy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /buy command — alias for /balance (unified screen)."""
        await self.balance_command(update, context)

    # =========================================================================
    # Navigation callbacks
    # =========================================================================

    async def back_to_main_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle billing:back_main — return to unified balance screen."""
        if not update.callback_query or not update.effective_user:
            return

        try:
            await update.callback_query.answer()
            text, markup = await self._build_balance_text_and_markup(update.effective_user.id)
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in back_to_main_callback: {e}", exc_info=True)

    # =========================================================================
    # Subscription catalog
    # =========================================================================

    async def _build_subscriptions_catalog(self) -> tuple[str, InlineKeyboardMarkup | None]:
        """Build subscription catalog — single column with RUB prices and discounts."""
        tiers = await self.subscription_service.get_available_tiers()

        if not tiers:
            no_buttons = [[InlineKeyboardButton("« Назад", callback_data="billing:back_main")]]
            return "Подписки сейчас недоступны.", InlineKeyboardMarkup(no_buttons)

        lines = ["🔔 Доступные подписки:\n"]
        buttons: list[list[InlineKeyboardButton]] = []

        for tier in tiers:
            lines.append(f"⭐ {tier.name} — {tier.daily_limit_minutes:.0f} мин/день")
            if tier.description:
                lines.append(f"   {tier.description}")

            prices = await self.subscription_service.get_tier_prices(tier.id)
            if prices:
                for price in prices:
                    period_label = _period_label(price.period)
                    btn_text = f"{tier.name} ({period_label}) — {price.amount_rub:.0f} ₽"
                    buttons.append(
                        [
                            InlineKeyboardButton(
                                btn_text,
                                callback_data=f"billing:sub_detail:{tier.id}:{price.period}",
                            )
                        ]
                    )

        buttons.append([InlineKeyboardButton("« Назад", callback_data="billing:back_main")])

        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    async def subscriptions_catalog_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle billing:subscriptions — show subscription catalog."""
        if not update.callback_query:
            return

        try:
            await update.callback_query.answer()
            text, markup = await self._build_subscriptions_catalog()
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in subscriptions_catalog_callback: {e}", exc_info=True)

    # =========================================================================
    # Package catalog
    # =========================================================================

    async def _build_packages_catalog(self) -> tuple[str, InlineKeyboardMarkup | None]:
        """Build packages catalog — single column with RUB prices."""
        packages = await self.payment_service.get_active_packages()

        if not packages:
            no_buttons = [[InlineKeyboardButton("« Назад", callback_data="billing:back_main")]]
            return "Пакеты минут сейчас недоступны.", InlineKeyboardMarkup(no_buttons)

        lines = ["📦 Пакеты минут:\n"]
        buttons: list[list[InlineKeyboardButton]] = []

        for pkg in packages:
            lines.append(f"• {pkg.name} ({pkg.minutes:.0f} мин) — {pkg.price_rub:.0f} ₽")
            btn_text = f"{pkg.name} — {pkg.price_rub:.0f} ₽"
            buttons.append(
                [
                    InlineKeyboardButton(
                        btn_text,
                        callback_data=f"billing:pkg_detail:{pkg.id}",
                    )
                ]
            )

        buttons.append([InlineKeyboardButton("« Назад", callback_data="billing:back_main")])

        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    async def packages_catalog_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle billing:packages — show packages catalog."""
        if not update.callback_query:
            return

        try:
            await update.callback_query.answer()
            text, markup = await self._build_packages_catalog()
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in packages_catalog_callback: {e}", exc_info=True)

    # =========================================================================
    # Detail screens
    # =========================================================================

    async def subscription_detail_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle billing:sub_detail:{tier_id}:{period} — show subscription detail with payment buttons."""
        if not update.callback_query or not update.callback_query.data:
            return

        try:
            await update.callback_query.answer()

            parts = update.callback_query.data.split(":")
            tier_id = int(parts[2])
            period = parts[3]

            tier = await self.subscription_service.get_tier_by_id(tier_id)
            if not tier:
                await update.callback_query.edit_message_text("Тариф не найден.")
                return

            prices = await self.subscription_service.get_tier_prices(tier_id)
            price = next((p for p in prices if p.period == period), None)
            if not price:
                await update.callback_query.edit_message_text("Цена не найдена.")
                return

            period_label = _period_label(period)

            lines = [
                f"⭐ Подписка {tier.name} — {period_label}\n",
                f"📊 Дневной лимит: {tier.daily_limit_minutes:.0f} мин/день",
            ]
            if price.description:
                lines.append(f"\n📝 {price.description}")
            elif tier.description:
                lines.append(f"\n📝 {tier.description}")

            lines.append(f"\n💰 Стоимость: {price.amount_rub:.0f} ₽ / {price.amount_stars} ⭐")

            buttons = [
                [
                    InlineKeyboardButton(
                        f"🇷🇺 💳 Карта РФ — {price.amount_rub:.0f} ₽",
                        callback_data=f"sub_card:{tier_id}:{period}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"🌟 Telegram Stars — {price.amount_stars} ⭐",
                        callback_data=f"sub_stars:{tier_id}:{period}",
                    )
                ],
                [InlineKeyboardButton("« Назад", callback_data="billing:subscriptions")],
            ]

            await update.callback_query.edit_message_text(
                "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.error(f"Error in subscription_detail_callback: {e}", exc_info=True)

    async def package_detail_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle billing:pkg_detail:{package_id} — show package detail with payment buttons."""
        if not update.callback_query or not update.callback_query.data:
            return

        try:
            await update.callback_query.answer()

            parts = update.callback_query.data.split(":")
            package_id = int(parts[2])

            async with get_session() as session:
                repo = MinutePackageRepository(session)
                pkg = await repo.get_by_id(package_id)

            if not pkg:
                await update.callback_query.edit_message_text("Пакет не найден.")
                return

            lines = [
                f"📦 {pkg.name}\n",
                f"⏱ Количество минут: {pkg.minutes:.0f}",
            ]
            if pkg.description:
                lines.append(f"\n📝 {pkg.description}")

            lines.append(f"\n💰 Стоимость: {pkg.price_rub:.0f} ₽ / {pkg.price_stars} ⭐")

            buttons = [
                [
                    InlineKeyboardButton(
                        f"🇷🇺 💳 Карта РФ — {pkg.price_rub:.0f} ₽",
                        callback_data=f"pkg_card:{pkg.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"🌟 Telegram Stars — {pkg.price_stars} ⭐",
                        callback_data=f"pkg_stars:{pkg.id}",
                    )
                ],
                [InlineKeyboardButton("« Назад", callback_data="billing:packages")],
            ]

            await update.callback_query.edit_message_text(
                "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.error(f"Error in package_detail_callback: {e}", exc_info=True)

    # =========================================================================
    # Enhanced /start and /help
    # =========================================================================

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
            "- Подписки и пакеты минут: /buy\n\n"
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
            "/help — Показать эту справку\n"
            "/balance — Проверить баланс минут\n"
            "/buy — Купить подписку или пакет минут\n"
            "/stats — Посмотреть статистику\n\n"
            "Условия:\n"
            "- 10 бесплатных минут транскрибации в день\n"
            "- Бонусные и пакетные минуты тратятся после дневного лимита\n"
            "- Подписка увеличивает дневной лимит"
        )

        await update.message.reply_text(help_message)
