"""
Telegram Voice2Text Bot
Entry point for the application
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.config import settings
from src.storage.database import init_db, close_db
from src.transcription import get_transcription_router, shutdown_transcription_router, AudioHandler
from src.bot.handlers import BotHandlers
from src.services.queue_manager import QueueManager
from src.utils.logging_config import setup_logging, log_deployment_event, get_config_summary

# Setup centralized logging
APP_VERSION = os.getenv("APP_VERSION", "unknown")
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
SYSLOG_ENABLED = os.getenv("SYSLOG_ENABLED", "false").lower() == "true"
SYSLOG_HOST = os.getenv("SYSLOG_HOST")
SYSLOG_PORT = int(os.getenv("SYSLOG_PORT", "514"))

setup_logging(
    log_dir=LOG_DIR,
    version=APP_VERSION,
    log_level=settings.log_level,
    enable_syslog=SYSLOG_ENABLED,
    syslog_host=SYSLOG_HOST,
    syslog_port=SYSLOG_PORT,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main application entry point."""
    # Log deployment startup event
    log_deployment_event(
        log_dir=LOG_DIR,
        event="startup",
        version=APP_VERSION,
        config=get_config_summary(),
    )

    logger.info("Starting Telegram Voice2Text Bot")
    logger.info(f"Bot mode: {settings.bot_mode}")
    logger.info(f"Enabled providers: {settings.whisper_providers}")
    logger.info(f"Routing strategy: {settings.whisper_routing_strategy}")
    logger.info(f"Database: {settings.database_url}")

    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    # Initialize transcription router
    logger.info("Initializing transcription router...")
    transcription_router = get_transcription_router()
    logger.info("Transcription router initialized")

    # Initialize audio handler
    audio_handler = AudioHandler()
    logger.info("Audio handler initialized")

    # Initialize queue manager
    queue_manager = QueueManager(
        max_queue_size=settings.max_queue_size,
        max_concurrent=settings.max_concurrent_workers,
    )
    logger.info(
        f"Queue manager initialized (max_queue={settings.max_queue_size}, max_concurrent={settings.max_concurrent_workers})"
    )

    # Create bot handlers
    bot_handlers = BotHandlers(
        whisper_service=transcription_router,
        audio_handler=audio_handler,
        queue_manager=queue_manager,
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

            # Log ready event
            log_deployment_event(
                log_dir=LOG_DIR,
                event="ready",
                version=APP_VERSION,
            )

            # Keep running
            await asyncio.Event().wait()

        else:
            # Webhook mode (future implementation)
            logger.error("Webhook mode not yet implemented")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")

    finally:
        # Log shutdown event
        log_deployment_event(
            log_dir=LOG_DIR,
            event="shutdown",
            version=APP_VERSION,
        )

        # Cleanup
        logger.info("Cleaning up resources...")

        if application.updater and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
            await application.shutdown()

        # Stop queue worker
        await queue_manager.stop_worker()

        await shutdown_transcription_router()
        await close_db()

        logger.info("Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)
