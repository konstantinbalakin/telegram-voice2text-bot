"""
Broadcast notification utility for billing system launch.

Usage:
    TELEGRAM_BOT_TOKEN=your_token uv run python -m src.utils.billing_broadcast
"""

import asyncio
import logging
import os

from telegram import Bot

from src.storage.database import get_session
from src.storage.models import User

from sqlalchemy import select

logger = logging.getLogger(__name__)

BILLING_LAUNCH_MESSAGE = (
    "📢 Обновление бота!\n\n"
    "Мы вводим систему тарификации для устойчивого развития сервиса.\n\n"
    "🎁 Что вы получаете:\n"
    "• 10 бесплатных минут транскрипции в день\n"
    "• 60 бонусных минут в подарок (бессрочно)\n\n"
    "💡 Хотите больше? Доступны подписки и пакеты минут.\n"
    "Используйте /balance для проверки баланса.\n\n"
    "Спасибо, что пользуетесь нашим ботом! 🙏"
)


async def send_broadcast(bot_token: str, message: str) -> tuple[int, int]:
    """Send broadcast message to all users. Returns (sent_count, failed_count)."""
    bot = Bot(token=bot_token)
    sent = 0
    failed = 0

    async with get_session() as session:
        result = await session.execute(select(User.telegram_id))
        telegram_ids = [row[0] for row in result.fetchall()]

    for telegram_id in telegram_ids:
        try:
            await bot.send_message(chat_id=telegram_id, text=message)
            sent += 1
            logger.info(f"Sent broadcast to {telegram_id}")
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to send broadcast to {telegram_id}: {e}")
        await asyncio.sleep(0.05)  # Rate limiting

    logger.info(f"Broadcast complete: {sent} sent, {failed} failed")
    return sent, failed


async def main() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting billing launch broadcast...")
    sent, failed = await send_broadcast(bot_token, BILLING_LAUNCH_MESSAGE)
    logger.info(f"Done: {sent} sent, {failed} failed out of {sent + failed} total")


if __name__ == "__main__":
    asyncio.run(main())
