"""
Telegram Voice2Text Bot
Entry point for the application
"""

import asyncio
import logging
import sys

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.config import settings
from src.storage.database import init_db, close_db
from src.transcription.whisper_service import WhisperService
from src.transcription.audio_handler import AudioHandler
from src.bot.handlers import BotHandlers

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

    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    # Initialize Whisper service
    logger.info("Initializing Whisper service...")
    whisper_service = WhisperService(
        model_size=settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        max_workers=settings.max_concurrent_workers,
    )
    whisper_service.initialize()
    logger.info("Whisper service initialized")

    # Initialize audio handler
    audio_handler = AudioHandler()
    logger.info("Audio handler initialized")

    # Create bot handlers
    bot_handlers = BotHandlers(
        whisper_service=whisper_service,
        audio_handler=audio_handler,
    )

    # Build telegram bot application
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Register handlers
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("stats", bot_handlers.stats_command))
    application.add_handler(MessageHandler(filters.VOICE, bot_handlers.voice_message_handler))
    application.add_handler(MessageHandler(filters.AUDIO, bot_handlers.audio_message_handler))

    # Register error handler
    application.add_error_handler(bot_handlers.error_handler)

    logger.info("Bot handlers registered")

    # Start bot
    try:
        if settings.bot_mode == "polling":
            logger.info("Starting bot in polling mode...")
            await application.initialize()
            await application.start()
            if application.updater:
                await application.updater.start_polling(drop_pending_updates=True)
            logger.info("Bot is ready and running (polling mode)")

            # Keep running
            await asyncio.Event().wait()

        else:
            # Webhook mode (future implementation)
            logger.error("Webhook mode not yet implemented")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")

    finally:
        # Cleanup
        logger.info("Cleaning up resources...")

        if application.updater and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
            await application.shutdown()

        await whisper_service.shutdown()
        await close_db()

        logger.info("Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)
