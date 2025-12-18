"""
Telegram Voice2Text Bot
Entry point for the application
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    TypeHandler,
)

from src.config import settings
from src.storage.database import init_db, close_db, get_session
from src.storage.repositories import (
    TranscriptionStateRepository,
    TranscriptionVariantRepository,
    TranscriptionSegmentRepository,
    UsageRepository,
)
from src.transcription import get_transcription_router, shutdown_transcription_router, AudioHandler
from src.services.prompt_loader import load_prompt
from src.bot.handlers import BotHandlers
from src.bot.callbacks import CallbackHandlers
from src.services.queue_manager import QueueManager
from src.services.llm_service import LLMFactory, LLMService
from src.services.text_processor import TextProcessor
from src.services.telegram_client import TelegramClientService
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

    # Initialize LLM service for text refinement
    llm_service = None
    if settings.llm_refinement_enabled:
        try:
            # Load refinement prompt from file
            try:
                refinement_prompt = load_prompt("refinement")
                logger.info("Loaded refinement prompt from file")
            except (FileNotFoundError, IOError) as e:
                logger.warning(f"Failed to load refinement prompt: {e}")
                # Fallback to default prompt
                refinement_prompt = """Ниже приведён текст из расшифровки аудиозаписи. Некоторые слова могут быть неточными. Если слово нормальное, то не нужно его изменять. А если не очень, то попробуй подобрать наиболее правильный по смыслу исправленный вариант. Отвечай только итоговым исправленным вариантом. Без другого лишнего текста. Вот исходный текст:

{text}"""
                logger.info("Using default refinement prompt")

            llm_provider = LLMFactory.create_provider(settings)
            if llm_provider:
                llm_service = LLMService(
                    provider=llm_provider,
                    prompt=refinement_prompt,
                )
                logger.info(
                    f"LLM service initialized (provider={settings.llm_provider}, "
                    f"model={settings.llm_model})"
                )
            else:
                logger.warning(
                    "LLM refinement enabled but no provider available (missing API key?)"
                )
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")
            logger.warning("Continuing without LLM refinement")
    else:
        logger.info("LLM refinement disabled")

    # Initialize Telethon Client API for large files (>20 MB)
    telegram_client = None
    if settings.telethon_enabled:
        try:
            telegram_client = TelegramClientService()
            await telegram_client.start()
            logger.info(
                "Telethon Client API enabled for large files "
                f"(session: {settings.telethon_session_name}.session)"
            )
        except ValueError as e:
            logger.warning(f"Telethon Client API disabled: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Telethon client: {e}", exc_info=True)
            logger.warning("Large file support (>20 MB) disabled")
    else:
        logger.info("Telethon Client API disabled (max file size: 20 MB)")

    # Create text processor for interactive modes and StructureStrategy
    text_processor = None
    if llm_service:
        text_processor = TextProcessor(llm_service)
        logger.info("TextProcessor created for interactive modes")
    else:
        logger.warning(
            "LLM service not available - structured mode will be disabled even if flag is set"
        )

    # Create bot handlers
    bot_handlers = BotHandlers(
        whisper_service=transcription_router,
        audio_handler=audio_handler,
        queue_manager=queue_manager,
        llm_service=llm_service,
        telegram_client=telegram_client,
        text_processor=text_processor,
    )

    # Build telegram bot application
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Debug: Log all incoming updates
    async def debug_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Debug handler to log all incoming updates."""
        logger.debug(f"=== INCOMING UPDATE === type: {type(update)}")
        if update.callback_query:
            logger.debug(f"  -> CallbackQuery detected! data: {update.callback_query.data}")
        if update.message:
            logger.debug(
                f"  -> Message detected! text: {update.message.text if update.message.text else 'N/A'}"
            )

    # Register debug handler FIRST (lowest priority, runs for all updates)
    application.add_handler(TypeHandler(Update, debug_all_updates), group=999)

    # Register handlers
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("stats", bot_handlers.stats_command))
    application.add_handler(MessageHandler(filters.VOICE, bot_handlers.voice_message_handler))
    application.add_handler(MessageHandler(filters.AUDIO, bot_handlers.audio_message_handler))

    # Register callback query handler for interactive transcription
    if settings.interactive_mode_enabled:
        # Create callback handlers with repositories (they need session, created on-demand)
        async def callback_query_wrapper(
            update: object, context: ContextTypes.DEFAULT_TYPE
        ) -> None:
            """Wrapper to create repositories with session for each callback."""
            logger.debug(f"callback_query_wrapper called! update type: {type(update)}")
            if hasattr(update, "callback_query"):
                logger.debug(f"callback_query data: {update.callback_query.data if update.callback_query else 'None'}")  # type: ignore[attr-defined]
            async with get_session() as session:
                state_repo = TranscriptionStateRepository(session)
                variant_repo = TranscriptionVariantRepository(session)
                segment_repo = TranscriptionSegmentRepository(session)
                usage_repo = UsageRepository(session)
                callback_handlers = CallbackHandlers(
                    state_repo, variant_repo, segment_repo, usage_repo, text_processor, bot_handlers
                )
                await callback_handlers.handle_callback_query(update, context)  # type: ignore[arg-type]

        application.add_handler(CallbackQueryHandler(callback_query_wrapper))
        logger.info("Interactive transcription enabled - callback handlers registered")
    else:
        logger.info("Interactive transcription disabled")

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
                # IMPORTANT: allowed_updates must include "callback_query" for inline buttons to work
                await application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES,
                )
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

        # Close LLM service
        if llm_service:
            await llm_service.close()
            logger.info("LLM service closed")

        # Stop Telethon client
        if telegram_client:
            await telegram_client.stop()
            logger.info("Telethon client stopped")

        await shutdown_transcription_router()
        await close_db()

        logger.info("Cleanup complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)
