"""
Telegram Voice2Text Bot
Entry point for the application
"""
import asyncio
import logging
import sys

from src.config import settings

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level.upper()),
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main application entry point."""
    logger.info("Starting Telegram Voice2Text Bot")
    logger.info(f"Bot mode: {settings.bot_mode}")
    logger.info(f"Whisper model: {settings.whisper_model_size}")
    logger.info(f"Database: {settings.database_url}")

    # TODO: Initialize components
    # - Database
    # - Whisper service
    # - Queue manager
    # - Bot

    logger.info("Bot is ready and running...")

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)
