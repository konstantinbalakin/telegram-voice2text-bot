"""Telegram bot handlers for voice message processing."""

import asyncio
import io
import logging
import shutil
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Optional
from telegram import Update, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from src.config import settings
from src.storage.database import get_session
from src.storage.repositories import (
    UserRepository,
    UsageRepository,
    TranscriptionStateRepository,
    TranscriptionSegmentRepository,
    TranscriptionVariantRepository,
)
from src.transcription.routing.router import TranscriptionRouter
from src.transcription.routing.strategies import HybridStrategy
from src.transcription.audio_handler import AudioHandler
from src.transcription.models import TranscriptionContext, TranscriptionResult
from src.services.queue_manager import QueueManager, TranscriptionRequest
from src.services.progress_tracker import ProgressTracker
from src.services.llm_service import LLMService
from src.services.telegram_client import TelegramClientService
from src.bot.keyboards import create_transcription_keyboard

logger = logging.getLogger(__name__)

# Telegram message length limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_text(
    text: str,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
    header_reserve: int = 50,
) -> list[str]:
    """Split text into chunks that fit Telegram message length limit.

    Args:
        text: Text to split
        max_length: Maximum length of each chunk (default: 4096)
        header_reserve: Reserve space for header like "📝 Часть 1/10\n\n"

    Returns:
        List of text chunks
    """
    # Effective max length accounting for potential header
    effective_max = max_length - header_reserve

    if len(text) <= max_length:
        return [text]

    chunks = []

    # Simple approach: split by character count with smart breaks
    while text:
        if len(text) <= effective_max:
            chunks.append(text)
            break

        # Find best split point within limit
        chunk = text[:effective_max]

        # Try to split at paragraph boundary (double newline)
        split_pos = chunk.rfind("\n\n")
        if split_pos > effective_max * 0.5:  # At least 50% of chunk
            chunks.append(text[:split_pos])
            text = text[split_pos + 2 :]  # Skip the \n\n
            continue

        # Try to split at single newline
        split_pos = chunk.rfind("\n")
        if split_pos > effective_max * 0.5:
            chunks.append(text[:split_pos])
            text = text[split_pos + 1 :]  # Skip the \n
            continue

        # Try to split at sentence boundary
        split_pos = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
        if split_pos > effective_max * 0.5:
            chunks.append(text[: split_pos + 1])  # Include punctuation
            text = text[split_pos + 2 :]  # Skip punctuation and space
            continue

        # Try to split at word boundary
        split_pos = chunk.rfind(" ")
        if split_pos > 0:
            chunks.append(text[:split_pos])
            text = text[split_pos + 1 :]  # Skip the space
            continue

        # No good split point found, force split
        chunks.append(text[:effective_max])
        text = text[effective_max:]

    return chunks


def save_audio_file_for_retranscription(
    temp_file_path: Path, usage_id: int, file_id: str
) -> Optional[Path]:
    """Save audio file to persistent storage for retranscription (Phase 8).

    Args:
        temp_file_path: Temporary file path from audio handler
        usage_id: Usage record ID
        file_id: Telegram file ID

    Returns:
        Path to saved file or None if saving failed or retranscription is disabled
    """
    if not settings.enable_retranscribe:
        logger.debug("Retranscription disabled, skipping file save")
        return None

    try:
        # Create persistent directory if doesn't exist
        persistent_dir = Path(settings.persistent_audio_dir)
        persistent_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename
        file_extension = temp_file_path.suffix or ".ogg"
        permanent_path = persistent_dir / f"{usage_id}_{file_id}{file_extension}"

        # Copy file to permanent storage
        shutil.copy2(temp_file_path, permanent_path)
        logger.info(f"Audio file saved for retranscription: {permanent_path}")

        return permanent_path

    except Exception as e:
        logger.error(f"Failed to save audio file for retranscription: {e}", exc_info=True)
        return None


class BotHandlers:
    """Telegram bot handlers for processing voice messages with queue management."""

    def __init__(
        self,
        whisper_service: TranscriptionRouter,
        audio_handler: AudioHandler,
        queue_manager: QueueManager,
        llm_service: Optional[LLMService] = None,
        telegram_client: Optional[TelegramClientService] = None,
    ):
        """Initialize bot handlers.

        Args:
            whisper_service: Transcription router for transcription
            audio_handler: Audio handler for file operations
            queue_manager: Queue manager for request handling
            llm_service: Optional LLM service for text refinement
            telegram_client: Optional Telegram Client API service for large files
        """
        self.transcription_router = whisper_service
        self.audio_handler = audio_handler
        self.queue_manager = queue_manager
        self.llm_service = llm_service
        self.telegram_client = telegram_client

        # Register callback for queue updates
        self.queue_manager.set_on_queue_changed(self._update_queue_messages)

        # Start queue worker
        asyncio.create_task(self.queue_manager.start_worker(self._process_transcription))

    async def _update_queue_messages(self) -> None:
        """Update all pending queue messages with new positions and wait times.

        Called when queue changes (request starts processing).
        """
        pending_requests = self.queue_manager.get_pending_requests()

        for i, request in enumerate(pending_requests):
            position = i + 1
            wait_time, processing_time = self.queue_manager.get_estimated_wait_time_by_id(
                request.id, settings.progress_rtf
            )

            try:
                # Format wait time nicely
                if wait_time < 60:
                    wait_str = f"~{int(wait_time)}с"
                else:
                    minutes = int(wait_time // 60)
                    seconds = int(wait_time % 60)
                    wait_str = f"~{minutes}м {seconds}с"

                if processing_time < 60:
                    proc_str = f"~{int(processing_time)}с"
                else:
                    minutes = int(processing_time // 60)
                    seconds = int(processing_time % 60)
                    proc_str = f"~{minutes}м {seconds}с"

                message_text = (
                    f"📋 В очереди: позиция {position}\n"
                    f"⏱️ Ожидание в очереди: {wait_str}\n"
                    f"🎯 Обработка вашего сообщения: {proc_str}"
                )

                await request.status_message.edit_text(message_text)
                logger.debug(
                    f"Updated queue message for request {request.id} at position {position}"
                )

            except Exception as e:
                # Ignore errors (message might be deleted, etc.)
                logger.debug(f"Failed to update queue message for {request.id}: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        user = update.effective_user
        if not user:
            return

        logger.debug(f"start_command: user_id={user.id}, username={user.username}")

        # Register or get existing user from database
        async with get_session() as session:
            user_repo = UserRepository(session)

            # Check if user exists
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                logger.debug(f"Creating new user: telegram_id={user.id}")
                # Create new user
                await user_repo.create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
            else:
                logger.debug(f"Existing user: id={db_user.id}, telegram_id={user.id}")

        welcome_message = (
            f"Привет, {user.first_name}!\n\n"
            "Я бот для транскрибации голосовых сообщений.\n\n"
            "Просто отправь мне голосовое сообщение, и я преобразую его в текст.\n\n"
            "Доступные команды:\n"
            "/start - Показать это сообщение\n"
            "/help - Помощь\n"
            "/stats - Статистика использования"
        )

        if update.message:
            await update.message.reply_text(welcome_message)
        logger.info(f"User {user.id} started the bot")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        help_message = (
            "Как пользоваться ботом:\n\n"
            "1. Отправьте мне голосовое сообщение\n"
            "2. Дождитесь обработки\n"
            "3. Получите текстовую расшифровку\n\n"
            "Поддерживаемые форматы:\n"
            "- Голосовые сообщения Telegram\n"
            "- Аудиофайлы (MP3, OGG, WAV)\n\n"
            "Доступные команды:\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n"
            "/stats - Посмотреть статистику"
        )

        if update.message:
            await update.message.reply_text(help_message)
        if update.effective_user:
            logger.debug(f"help_command: user_id={update.effective_user.id}")
            logger.info(f"User {update.effective_user.id} requested help")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        user = update.effective_user
        if not user:
            return

        logger.debug(f"stats_command: user_id={user.id}")

        async with get_session() as session:
            user_repo = UserRepository(session)
            usage_repo = UsageRepository(session)

            # Get user from database
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                if update.message:
                    await update.message.reply_text("Пользователь не найден. Используйте /start")
                return

            # Get transcription statistics
            usages = await usage_repo.get_by_user_id(db_user.id)
            total_count = len(usages)

            if total_count == 0:
                if update.message:
                    await update.message.reply_text(
                        "У вас пока нет обработанных голосовых сообщений.\n"
                        "Отправьте голосовое сообщение, чтобы начать!"
                    )
                return

            # Calculate statistics
            total_duration = sum(u.voice_duration_seconds or 0 for u in usages)
            avg_duration = total_duration / total_count if total_count > 0 else 0

            stats_message = (
                f"Ваша статистика:\n\n"
                f"Всего обработано: {total_count} сообщений\n"
                f"Общая продолжительность: {total_duration:.1f} сек\n"
                f"Средняя длительность: {avg_duration:.1f} сек\n"
                f"Дата регистрации: {db_user.created_at.strftime('%d.%m.%Y')}"
            )

            if update.message:
                await update.message.reply_text(stats_message)
            logger.info(f"User {user.id} requested statistics")

    async def voice_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle voice messages with queue management.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        user = update.effective_user
        if not user or not update.message:
            return

        voice = update.message.voice
        if not voice:
            return

        # Convert duration to int early for validation
        duration_seconds = 0
        if voice.duration:
            if isinstance(voice.duration, timedelta):
                duration_seconds = int(voice.duration.total_seconds())
            else:
                duration_seconds = int(voice.duration)

        logger.debug(
            f"voice_message_handler: user_id={user.id}, file_id={voice.file_id}, "
            f"duration={duration_seconds}s, file_size={voice.file_size}"
        )

        # 1. VALIDATE DURATION
        if duration_seconds > settings.max_voice_duration_seconds:
            await update.message.reply_text(
                f"⚠️ Максимальная длительность: {settings.max_voice_duration_seconds}с "
                f"({settings.max_voice_duration_seconds // 60} мин)\n\n"
                f"Ваш файл: {duration_seconds}с ({duration_seconds // 60} мин {duration_seconds % 60}с)"
            )
            logger.warning(
                f"User {user.id} rejected: duration {duration_seconds}s > {settings.max_voice_duration_seconds}s"
            )
            return

        # 2. CHECK QUEUE CAPACITY
        queue_depth = self.queue_manager.get_queue_depth()
        logger.debug(f"Queue check: depth={queue_depth}, max={settings.max_queue_size}")
        if queue_depth >= settings.max_queue_size:
            await update.message.reply_text(
                "⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут.\n\n"
                f"В очереди сейчас: {queue_depth} запросов"
            )
            logger.warning(
                f"User {user.id} rejected: queue full ({queue_depth}/{settings.max_queue_size})"
            )
            return

        # Check file size
        # - If Client API enabled: allow up to 2 GB
        # - If Client API disabled: limit to 20 MB (Bot API limit)
        if voice.file_size:
            if settings.telethon_enabled and self.telegram_client:
                # Client API available: allow files up to 2 GB
                max_size = 2 * 1024 * 1024 * 1024  # 2 GB
                if voice.file_size > max_size:
                    file_size_mb = voice.file_size / 1024 / 1024
                    await update.message.reply_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        "Максимальный размер: 2 ГБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Пожалуйста, отправьте файл меньшего размера."
                    )
                    logger.warning(
                        f"User {user.id} sent file too large: {file_size_mb:.1f} MB (max: 2 GB)"
                    )
                    return
            else:
                # Client API not available: limit to Bot API's 20 MB
                if voice.file_size > settings.max_file_size_bytes:
                    max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                    file_size_mb = voice.file_size / 1024 / 1024
                    await update.message.reply_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Пожалуйста, отправьте более короткое голосовое сообщение."
                    )
                    logger.warning(
                        f"User {user.id} sent file too large: {file_size_mb:.1f} MB "
                        f"(max: {max_size_mb:.0f} MB, Client API disabled)"
                    )
                    return

        # Send initial status
        status_msg = await update.message.reply_text("📥 Загружаю файл...")

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)
                usage_repo = UsageRepository(session)

                # Get or create user
                db_user = await user_repo.get_by_telegram_id(user.id)
                if not db_user:
                    db_user = await user_repo.create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )

                # STAGE 1: Create usage record on download start
                usage = await usage_repo.create(
                    user_id=db_user.id,
                    voice_file_id=voice.file_id,
                )
                logger.info(f"Usage record {usage.id} created for user {user.id}")

            # Download voice file (hybrid: Bot API for ≤20MB, Client API for >20MB)
            if voice.file_size and voice.file_size > settings.max_file_size_bytes:
                # Large file: use Client API if available
                if self.telegram_client and settings.telethon_enabled:
                    logger.info(
                        f"File size {voice.file_size} bytes exceeds Bot API limit "
                        f"({settings.max_file_size_bytes} bytes), using Client API"
                    )
                    file_path = await self.telegram_client.download_large_file(
                        message_id=update.message.message_id,
                        chat_id=update.message.chat_id,
                        output_dir=self.audio_handler.temp_dir,
                    )
                    if not file_path:
                        raise RuntimeError("Client API download returned None")
                else:
                    # Client API not available - should not reach here due to earlier check
                    # But kept as safety fallback
                    max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                    file_size_mb = voice.file_size / 1024 / 1024
                    await status_msg.edit_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Client API не настроен. Пожалуйста, отправьте более короткое сообщение."
                    )
                    logger.warning(f"User {user.id} sent large file but Client API unavailable")
                    return
            else:
                # Normal file: use Bot API (existing flow)
                voice_file = await context.bot.get_file(voice.file_id)
                file_path = await self.audio_handler.download_voice_message(
                    voice_file, voice.file_id
                )

            logger.info(f"File downloaded: {file_path}")

            # Phase 8: Save audio file for retranscription
            persistent_path = save_audio_file_for_retranscription(
                Path(file_path), usage.id, voice.file_id
            )

            # STAGE 2: Update with duration after download (+ file path for retranscription)
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=usage.id,
                    voice_duration_seconds=duration_seconds,
                    original_file_path=str(persistent_path) if persistent_path else None,
                )
                logger.info(f"Usage record {usage.id} updated with duration {duration_seconds}s")

            # Create transcription context
            transcription_context = TranscriptionContext(
                user_id=user.id,
                duration_seconds=duration_seconds,
                file_size_bytes=voice.file_size or 0,
                language="ru",
            )

            # Check if benchmark mode is enabled
            if self.transcription_router.strategy.is_benchmark_mode():
                # Run benchmark
                logger.info("Running benchmark on voice message...")
                report = await self.transcription_router.run_benchmark(
                    file_path, transcription_context
                )

                # Save best result to database
                successful_results = [r for r in report.results if r.error is None]
                if successful_results:
                    # Use fastest successful result
                    best_result = report.get_sorted_by_speed()[0]
                    await usage_repo.create(
                        user_id=db_user.id,
                        voice_duration_seconds=duration_seconds,
                        voice_file_id=voice.file_id,
                        transcription_length=len(best_result.text),
                        model_size=best_result.model_name,
                        processing_time_seconds=best_result.processing_time,
                    )

                # Clean up files
                self.audio_handler.cleanup_file(file_path)

                # Generate and send benchmark report
                report_text = report.to_markdown()

                # Telegram has 4096 character limit, split if needed
                if len(report_text) <= 4096:
                    await status_msg.edit_text(report_text, parse_mode="Markdown")
                else:
                    # Send message about successful results first
                    if successful_results:
                        best_result = report.get_sorted_by_speed()[0]
                        await status_msg.edit_text(
                            f"✅ Benchmark завершен!\n\n"
                            f"Лучший результат: {best_result.config.display_name if best_result.config else best_result.provider_used}\n"
                            f"Скорость: {best_result.processing_time:.2f}s (RTF: {best_result.realtime_factor:.2f}x)\n\n"
                            f"Транскрипция:\n{best_result.text}"
                        )
                    else:
                        await status_msg.edit_text("❌ Все модели не смогли обработать аудио")

                    # Send report in chunks
                    chunks = [report_text[i : i + 4096] for i in range(0, len(report_text), 4096)]
                    for chunk in chunks:
                        await update.message.reply_text(chunk, parse_mode="Markdown")

                logger.info(f"Benchmark completed for user {user.id}")

            else:
                # Normal transcription mode with queue
                # Create transcription request
                request = TranscriptionRequest(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    file_path=file_path,
                    duration_seconds=duration_seconds,
                    context=transcription_context,
                    status_message=status_msg,
                    user_message=update.message,
                    usage_id=usage.id,
                )

                logger.debug(
                    f"Transcription request created: id={request.id}, user_id={user.id}, "
                    f"duration={duration_seconds}s, file_path={file_path}"
                )

                # Enqueue request
                try:
                    queue_position = await self.queue_manager.enqueue(request)
                    logger.debug(f"Request enqueued: id={request.id}, position={queue_position}")
                    active_workers = self.queue_manager.get_processing_count()

                    # Show queue position or immediate start
                    # Position 1 with no active workers = starts immediately
                    # Position 1 with active workers = waiting for current to finish
                    # Position 2+ = waiting in queue
                    if queue_position > 1 or active_workers > 0:
                        # Request is in queue, waiting
                        # Get actual position in pending queue (not absolute position)
                        actual_position = self.queue_manager.get_queue_position_by_id(request.id)
                        wait_time, processing_time = (
                            self.queue_manager.get_estimated_wait_time_by_id(
                                request.id, settings.progress_rtf
                            )
                        )

                        # Format wait time nicely
                        if wait_time < 60:
                            wait_str = f"~{int(wait_time)}с"
                        else:
                            minutes = int(wait_time // 60)
                            seconds = int(wait_time % 60)
                            wait_str = f"~{minutes}м {seconds}с"

                        if processing_time < 60:
                            proc_str = f"~{int(processing_time)}с"
                        else:
                            minutes = int(processing_time // 60)
                            seconds = int(processing_time % 60)
                            proc_str = f"~{minutes}м {seconds}с"

                        await status_msg.edit_text(
                            f"📋 В очереди: позиция {actual_position}\n"
                            f"⏱️ Ожидание в очереди: {wait_str}\n"
                            f"🎯 Обработка вашего сообщения: {proc_str}"
                        )
                        logger.info(f"Request {request.id} enqueued at position {actual_position}")
                    else:
                        # Request will start immediately (position 1, no active workers)
                        await status_msg.edit_text("⚙️ Начинаю обработку...")
                        logger.info(f"Request {request.id} starting immediately")

                except asyncio.QueueFull:
                    # Queue full (shouldn't happen due to check above, but safety)
                    await status_msg.edit_text(
                        "⚠️ Очередь переполнена. Пожалуйста, попробуйте позже."
                    )
                    self.audio_handler.cleanup_file(file_path)
                    return

                # Note: Actual processing happens in _process_transcription callback
                # which is called by queue worker. User gets updates via status_msg.

        except BadRequest as e:
            # Handle Telegram API specific errors
            if "File is too big" in str(e):
                max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                logger.warning(f"User {user.id} file too big for Telegram API: {e}")
                try:
                    await status_msg.edit_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n\n"
                        "Пожалуйста, отправьте более короткое голосовое сообщение."
                    )
                except Exception:
                    pass
            else:
                logger.error(f"Telegram API error: {e}", exc_info=True)
                try:
                    await status_msg.edit_text(
                        "❌ Произошла ошибка Telegram API. " "Пожалуйста, попробуйте еще раз."
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error handling voice message: {e}", exc_info=True)
            try:
                await status_msg.edit_text(
                    "❌ Произошла ошибка при обработке голосового сообщения. "
                    "Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                pass

    async def audio_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle audio file messages with queue management.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        user = update.effective_user
        if not user or not update.message:
            return

        audio = update.message.audio
        if not audio:
            return

        # Convert duration to int early for validation
        duration_seconds = 0
        if audio.duration:
            if isinstance(audio.duration, timedelta):
                duration_seconds = int(audio.duration.total_seconds())
            else:
                duration_seconds = int(audio.duration)

        # 1. VALIDATE DURATION
        if duration_seconds > settings.max_voice_duration_seconds:
            await update.message.reply_text(
                f"⚠️ Максимальная длительность: {settings.max_voice_duration_seconds}с "
                f"({settings.max_voice_duration_seconds // 60} мин)\n\n"
                f"Ваш файл: {duration_seconds}с ({duration_seconds // 60} мин {duration_seconds % 60}с)"
            )
            logger.warning(
                f"User {user.id} rejected: duration {duration_seconds}s > {settings.max_voice_duration_seconds}s"
            )
            return

        # 2. CHECK QUEUE CAPACITY
        queue_depth = self.queue_manager.get_queue_depth()
        logger.debug(f"Queue check: depth={queue_depth}, max={settings.max_queue_size}")
        if queue_depth >= settings.max_queue_size:
            await update.message.reply_text(
                "⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут.\n\n"
                f"В очереди сейчас: {queue_depth} запросов"
            )
            logger.warning(
                f"User {user.id} rejected: queue full ({queue_depth}/{settings.max_queue_size})"
            )
            return

        # 3. CHECK FILE SIZE
        # - If Client API enabled: allow up to 2 GB
        # - If Client API disabled: limit to 20 MB (Bot API limit)
        if audio.file_size:
            if settings.telethon_enabled and self.telegram_client:
                # Client API available: allow files up to 2 GB
                max_size = 2 * 1024 * 1024 * 1024  # 2 GB
                if audio.file_size > max_size:
                    file_size_mb = audio.file_size / 1024 / 1024
                    await update.message.reply_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        "Максимальный размер: 2 ГБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Пожалуйста, отправьте файл меньшего размера."
                    )
                    logger.warning(
                        f"User {user.id} sent audio file too large: {file_size_mb:.1f} MB (max: 2 GB)"
                    )
                    return
            else:
                # Client API not available: limit to Bot API's 20 MB
                if audio.file_size > settings.max_file_size_bytes:
                    max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                    file_size_mb = audio.file_size / 1024 / 1024
                    await update.message.reply_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Пожалуйста, отправьте аудиофайл меньшего размера."
                    )
                    logger.warning(
                        f"User {user.id} sent audio file too large: {file_size_mb:.1f} MB "
                        f"(max: {max_size_mb:.0f} MB, Client API disabled)"
                    )
                    return

        # Send initial status
        status_msg = await update.message.reply_text("📥 Загружаю файл...")

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)
                usage_repo = UsageRepository(session)

                # Get or create user
                db_user = await user_repo.get_by_telegram_id(user.id)
                if not db_user:
                    db_user = await user_repo.create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )

                # STAGE 1: Create usage record on download start
                usage = await usage_repo.create(
                    user_id=db_user.id,
                    voice_file_id=audio.file_id,
                )
                logger.info(f"Usage record {usage.id} created for user {user.id}")

            # Download audio file (hybrid: Bot API for ≤20MB, Client API for >20MB)
            if audio.file_size and audio.file_size > settings.max_file_size_bytes:
                # Large file: use Client API if available
                if self.telegram_client and settings.telethon_enabled:
                    logger.info(
                        f"File size {audio.file_size} bytes exceeds Bot API limit "
                        f"({settings.max_file_size_bytes} bytes), using Client API"
                    )
                    file_path = await self.telegram_client.download_large_file(
                        message_id=update.message.message_id,
                        chat_id=update.message.chat_id,
                        output_dir=self.audio_handler.temp_dir,
                    )
                    if not file_path:
                        raise RuntimeError("Client API download returned None")
                else:
                    # Client API not available - should not reach here due to earlier check
                    # But kept as safety fallback
                    max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                    file_size_mb = audio.file_size / 1024 / 1024
                    await status_msg.edit_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Client API не настроен. Пожалуйста, отправьте файл меньшего размера."
                    )
                    logger.warning(
                        f"User {user.id} sent large audio file but Client API unavailable"
                    )
                    return
            else:
                # Normal file: use Bot API (existing flow)
                audio_file = await context.bot.get_file(audio.file_id)
                file_path = await self.audio_handler.download_voice_message(
                    audio_file, audio.file_id
                )

            logger.info(f"File downloaded: {file_path}")

            # Phase 8: Save audio file for retranscription
            persistent_path = save_audio_file_for_retranscription(
                Path(file_path), usage.id, audio.file_id
            )

            # STAGE 2: Update with duration after download (+ file path for retranscription)
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=usage.id,
                    voice_duration_seconds=duration_seconds,
                    original_file_path=str(persistent_path) if persistent_path else None,
                )
                logger.info(f"Usage record {usage.id} updated with duration {duration_seconds}s")

            # Create transcription context
            transcription_context = TranscriptionContext(
                user_id=user.id,
                duration_seconds=duration_seconds,
                file_size_bytes=audio.file_size or 0,
                language="ru",
            )

            # Check if benchmark mode is enabled
            if self.transcription_router.strategy.is_benchmark_mode():
                # Run benchmark
                logger.info("Running benchmark on audio file...")
                report = await self.transcription_router.run_benchmark(
                    file_path, transcription_context
                )

                # Save best result to database
                successful_results = [r for r in report.results if r.error is None]
                if successful_results:
                    # Use fastest successful result
                    best_result = report.get_sorted_by_speed()[0]
                    await usage_repo.create(
                        user_id=db_user.id,
                        voice_duration_seconds=duration_seconds,
                        voice_file_id=audio.file_id,
                        transcription_length=len(best_result.text),
                        model_size=best_result.model_name,
                        processing_time_seconds=best_result.processing_time,
                    )

                # Clean up files
                self.audio_handler.cleanup_file(file_path)

                # Generate and send benchmark report
                report_text = report.to_markdown()

                # Telegram has 4096 character limit, split if needed
                if len(report_text) <= 4096:
                    await status_msg.edit_text(report_text, parse_mode="Markdown")
                else:
                    # Send message about successful results first
                    if successful_results:
                        best_result = report.get_sorted_by_speed()[0]
                        await status_msg.edit_text(
                            f"✅ Benchmark завершен!\n\n"
                            f"Лучший результат: {best_result.config.display_name if best_result.config else best_result.provider_used}\n"
                            f"Скорость: {best_result.processing_time:.2f}s (RTF: {best_result.realtime_factor:.2f}x)\n\n"
                            f"Транскрипция:\n{best_result.text}"
                        )
                    else:
                        await status_msg.edit_text("❌ Все модели не смогли обработать аудио")

                    # Send report in chunks
                    chunks = [report_text[i : i + 4096] for i in range(0, len(report_text), 4096)]
                    for chunk in chunks:
                        await update.message.reply_text(chunk, parse_mode="Markdown")

                logger.info(f"Benchmark completed for user {user.id}")

            else:
                # Normal transcription mode with queue
                # Create transcription request
                request = TranscriptionRequest(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    file_path=file_path,
                    duration_seconds=duration_seconds,
                    context=transcription_context,
                    status_message=status_msg,
                    user_message=update.message,
                    usage_id=usage.id,
                )

                logger.debug(
                    f"Transcription request created: id={request.id}, user_id={user.id}, "
                    f"duration={duration_seconds}s, file_path={file_path}"
                )

                # Enqueue request
                try:
                    queue_position = await self.queue_manager.enqueue(request)
                    logger.debug(f"Request enqueued: id={request.id}, position={queue_position}")
                    active_workers = self.queue_manager.get_processing_count()

                    # Show queue position or immediate start
                    # Position 1 with no active workers = starts immediately
                    # Position 1 with active workers = waiting for current to finish
                    # Position 2+ = waiting in queue
                    if queue_position > 1 or active_workers > 0:
                        # Request is in queue, waiting
                        # Get actual position in pending queue (not absolute position)
                        actual_position = self.queue_manager.get_queue_position_by_id(request.id)
                        wait_time, processing_time = (
                            self.queue_manager.get_estimated_wait_time_by_id(
                                request.id, settings.progress_rtf
                            )
                        )

                        # Format wait time nicely
                        if wait_time < 60:
                            wait_str = f"~{int(wait_time)}с"
                        else:
                            minutes = int(wait_time // 60)
                            seconds = int(wait_time % 60)
                            wait_str = f"~{minutes}м {seconds}с"

                        if processing_time < 60:
                            proc_str = f"~{int(processing_time)}с"
                        else:
                            minutes = int(processing_time // 60)
                            seconds = int(processing_time % 60)
                            proc_str = f"~{minutes}м {seconds}с"

                        await status_msg.edit_text(
                            f"📋 В очереди: позиция {actual_position}\n"
                            f"⏱️ Ожидание в очереди: {wait_str}\n"
                            f"🎯 Обработка вашего сообщения: {proc_str}"
                        )
                        logger.info(f"Request {request.id} enqueued at position {actual_position}")
                    else:
                        # Request will start immediately (position 1, no active workers)
                        await status_msg.edit_text("⚙️ Начинаю обработку...")
                        logger.info(f"Request {request.id} starting immediately")

                except asyncio.QueueFull:
                    # Queue full (shouldn't happen due to check above, but safety)
                    await status_msg.edit_text(
                        "⚠️ Очередь переполнена. Пожалуйста, попробуйте позже."
                    )
                    self.audio_handler.cleanup_file(file_path)
                    return

                # Note: Actual processing happens in _process_transcription callback
                # which is called by queue worker. User gets updates via status_msg.

        except BadRequest as e:
            # Handle Telegram API specific errors
            if "File is too big" in str(e):
                max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                logger.warning(f"User {user.id} audio file too big for Telegram API: {e}")
                try:
                    await status_msg.edit_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n\n"
                        "Пожалуйста, отправьте аудиофайл меньшего размера."
                    )
                except Exception:
                    pass
            else:
                logger.error(f"Telegram API error: {e}", exc_info=True)
                try:
                    await status_msg.edit_text(
                        "❌ Произошла ошибка Telegram API. " "Пожалуйста, попробуйте еще раз."
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error handling audio file: {e}", exc_info=True)
            try:
                await status_msg.edit_text(
                    "❌ Произошла ошибка при обработке аудиофайла. "
                    "Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                pass

    async def _create_interactive_state_and_keyboard(
        self,
        usage_id: int,
        message_id: int,
        chat_id: int,
        result: TranscriptionResult,
        final_text: str,
        is_file_message: bool = False,
        file_message_id: Optional[int] = None,
    ) -> Optional["InlineKeyboardMarkup"]:
        """Create TranscriptionState, save segments, save original variant, and generate keyboard.

        Args:
            usage_id: Usage record ID
            message_id: Telegram message ID where transcription was sent (main message with keyboard)
            chat_id: Telegram chat ID
            result: TranscriptionResult with optional segments
            final_text: The final text that was sent to the user (original variant)
            is_file_message: Whether transcription was sent as file (True) or text (False)
            file_message_id: Message ID of the file message (if sent as file)

        Returns:
            InlineKeyboardMarkup or None if interactive mode disabled
        """
        logger.debug(
            f"_create_interactive_state_and_keyboard called: usage_id={usage_id}, "
            f"message_id={message_id}, is_file_message={is_file_message}, "
            f"file_message_id={file_message_id}, interactive_mode={settings.interactive_mode_enabled}"
        )

        if not settings.interactive_mode_enabled:
            logger.debug("Interactive mode disabled, returning None")
            return None

        try:
            async with get_session() as session:
                state_repo = TranscriptionStateRepository(session)
                segment_repo = TranscriptionSegmentRepository(session)
                variant_repo = TranscriptionVariantRepository(session)

                # Get existing state or create new one
                state = await state_repo.get_by_usage_id(usage_id)
                if not state:
                    # Create TranscriptionState
                    state = await state_repo.create(
                        usage_id=usage_id,
                        message_id=message_id,
                        chat_id=chat_id,
                        is_file_message=is_file_message,
                        file_message_id=file_message_id,
                    )
                    logger.debug(
                        f"TranscriptionState created: id={state.id}, usage_id={usage_id}, "
                        f"message_id={message_id}, is_file={is_file_message}, file_msg_id={file_message_id}"
                    )
                else:
                    logger.debug(
                        f"Using existing TranscriptionState: id={state.id}, usage_id={usage_id}"
                    )

                # Save original variant (Phase 2)
                await variant_repo.create(
                    usage_id=usage_id,
                    mode="original",
                    text_content=final_text,
                    generated_by="transcription",
                )
                logger.debug(f"Saved original variant for usage_id={usage_id}")

                # Save segments if available, duration exceeds threshold, and feature is enabled
                has_segments = False
                if (
                    settings.enable_timestamps_option
                    and result.segments
                    and result.audio_duration >= settings.timestamps_min_duration
                ):
                    segments_data = [
                        (i, seg.start, seg.end, seg.text) for i, seg in enumerate(result.segments)
                    ]
                    await segment_repo.create_batch(usage_id, segments_data)
                    has_segments = True
                    logger.debug(
                        f"Saved {len(segments_data)} segments for usage_id={usage_id}, "
                        f"duration={result.audio_duration:.1f}s"
                    )
                elif result.segments and not settings.enable_timestamps_option:
                    logger.debug(
                        "Segments not saved (timestamps feature disabled: "
                        "ENABLE_TIMESTAMPS_OPTION=false)"
                    )
                elif result.segments:
                    logger.debug(
                        f"Segments not saved (duration {result.audio_duration:.1f}s < "
                        f"threshold {settings.timestamps_min_duration}s)"
                    )

                # Generate keyboard
                keyboard = create_transcription_keyboard(state, has_segments, settings)
                return keyboard

        except Exception as e:
            logger.error(f"Failed to create interactive state: {e}", exc_info=True)
            return None

    async def _send_transcription_result(
        self,
        request: TranscriptionRequest,
        text: str,
        keyboard: Optional[InlineKeyboardMarkup],
        usage_id: int,
        prefix: str = "✅ Готово!\n\n",
    ) -> tuple[Message, Optional[Message]]:
        """Send transcription result as text message or file based on length.

        Args:
            request: Transcription request
            text: Text content to send
            keyboard: Inline keyboard markup (optional)
            usage_id: Usage record ID
            prefix: Optional prefix for short messages

        Returns:
            (main_message, file_message): Main message (with keyboard) and optional file message
        """
        if len(text) <= settings.file_threshold_chars:
            # Short text: send as single message
            msg = await request.user_message.reply_text(prefix + text, reply_markup=keyboard)
            logger.debug(
                f"Sent text result: usage_id={usage_id}, length={len(text)}, "
                f"threshold={settings.file_threshold_chars}"
            )
            return (msg, None)
        else:
            # Long text: send as file
            # Message 1: Info + keyboard
            info_msg = await request.user_message.reply_text(
                "📝 Транскрипция готова! Файл ниже ↓", reply_markup=keyboard
            )

            # Message 2: File
            file_obj = io.BytesIO(text.encode("utf-8"))
            file_obj.name = f"transcription_{usage_id}.txt"

            file_msg = await request.user_message.reply_document(
                document=file_obj,
                filename=file_obj.name,
                caption=f"📄 Транскрипция ({len(text)} символов)",
            )

            logger.debug(
                f"Sent file result: usage_id={usage_id}, length={len(text)}, "
                f"threshold={settings.file_threshold_chars}"
            )
            return (info_msg, file_msg)

    async def _send_draft_messages(
        self,
        request: TranscriptionRequest,
        draft_text: str,
    ) -> None:
        """Send draft text (as text or file based on length).

        Args:
            request: Transcription request (will populate draft_messages)
            draft_text: Draft transcription text to send
        """
        # Delete status message first
        try:
            await request.status_message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete status message: {e}")

        if len(draft_text) <= settings.file_threshold_chars:
            # Short draft: send as text message
            logger.debug(
                f"Sending short draft as text: request_id={request.id}, length={len(draft_text)}"
            )
            message = await request.user_message.reply_text(
                f"✅ Черновик готов:\n\n{draft_text}\n\n🔄 Улучшаю текст..."
            )
            request.draft_messages.append(message)
        else:
            # Long draft: send as file
            logger.debug(
                f"Sending long draft as file: request_id={request.id}, length={len(draft_text)}"
            )

            # Message 1: Info
            info_msg = await request.user_message.reply_text(
                "✅ Черновик готов! Файл ниже ↓\n\n🔄 Улучшаю текст..."
            )
            request.draft_messages.append(info_msg)

            # Message 2: File
            file_obj = io.BytesIO(draft_text.encode("utf-8"))
            file_obj.name = f"draft_{request.usage_id}.txt"

            file_msg = await request.user_message.reply_document(
                document=file_obj,
                filename=file_obj.name,
                caption=f"📄 Черновик ({len(draft_text)} символов)",
            )
            request.draft_messages.append(file_msg)

    async def _process_transcription(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Process transcription request (called by queue worker).

        Args:
            request: Transcription request from queue

        Returns:
            TranscriptionResult on success

        Raises:
            Exception on error
        """
        logger.info(f"Processing transcription request {request.id}")

        # Note: Status message already updated in voice_message_handler
        # No need to update again here to avoid "Message is not modified" error

        # Start progress tracker
        progress = ProgressTracker(
            message=request.status_message,
            duration_seconds=request.duration_seconds,
            rtf=settings.progress_rtf,
            update_interval=settings.progress_update_interval,
        )
        await progress.start()

        try:
            # === PREPROCESSING: Apply audio transformations ===
            processed_path = request.file_path
            try:
                processed_path = self.audio_handler.preprocess_audio(request.file_path)
                if processed_path != request.file_path:
                    logger.info(f"Audio preprocessed: {processed_path.name}")
            except Exception as e:
                logger.warning(f"Audio preprocessing failed: {e}, using original")
                processed_path = request.file_path

            # === TRANSCRIPTION: Get draft or final transcription ===
            result = await self.transcription_router.transcribe(
                processed_path,
                request.context,
            )

            # Stop progress updates
            await progress.stop()

            # === HYBRID STRATEGY: Check if LLM refinement needed ===
            needs_refinement = False
            if isinstance(self.transcription_router.strategy, HybridStrategy):
                # Type narrow: we know it's HybridStrategy here
                needs_refinement = self.transcription_router.strategy.requires_refinement(
                    request.duration_seconds
                )

            # Skip refinement if explicitly disabled (e.g., for retranscription)
            if request.context.disable_refinement:
                needs_refinement = False
                logger.info("LLM refinement disabled by context")

            final_text = result.text

            if needs_refinement and self.llm_service:
                # === STAGE 1: Send draft (handles both short and long) ===
                draft_text = result.text
                await self._send_draft_messages(request, draft_text)

                # === STAGE 2: Refine with LLM ===
                try:
                    llm_start = time.time()
                    refined_text = await self.llm_service.refine_transcription(draft_text)
                    llm_time = time.time() - llm_start
                    final_text = refined_text
                    logger.info(f"LLM refinement took {llm_time:.2f}s")

                    # === STAGE 4: Update database with LLM processing time ===
                    async with get_session() as session:
                        usage_repo = UsageRepository(session)
                        await usage_repo.update(
                            usage_id=request.usage_id,
                            llm_processing_time_seconds=llm_time,
                        )
                        logger.debug(f"LLM processing time saved to database: {llm_time:.2f}s")

                    # === Delete draft messages and send refined ===
                    # Delete all draft messages (if any)
                    for msg in request.draft_messages:
                        try:
                            await msg.delete()
                            logger.debug(f"Deleted draft message: request_id={request.id}")
                        except Exception as e:
                            logger.warning(f"Failed to delete draft message: {e}")

                    # If short draft was in status_message, need to handle it too
                    if not request.draft_messages:
                        try:
                            await request.status_message.delete()
                            logger.debug(
                                f"Deleted status message (short draft): request_id={request.id}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to delete status message: {e}")

                    # Create keyboard
                    keyboard = await self._create_interactive_state_and_keyboard(
                        usage_id=request.usage_id,
                        message_id=0,  # Will be updated after sending
                        chat_id=request.user_message.chat_id,
                        result=result,
                        final_text=refined_text,
                    )

                    # Send refined text (as text or file based on length)
                    main_msg, file_msg = await self._send_transcription_result(
                        request=request,
                        text=refined_text,
                        keyboard=keyboard,
                        usage_id=request.usage_id,
                        prefix="",
                    )

                    # Update state with correct message IDs
                    if keyboard:
                        async with get_session() as session:
                            state_repo = TranscriptionStateRepository(session)
                            state = await state_repo.get_by_usage_id(request.usage_id)
                            if state:
                                state.message_id = main_msg.message_id
                                state.is_file_message = file_msg is not None
                                state.file_message_id = file_msg.message_id if file_msg else None
                                await state_repo.update(state)
                                logger.debug(
                                    f"Updated state: message_id={main_msg.message_id}, "
                                    f"is_file={file_msg is not None}, "
                                    f"file_msg_id={file_msg.message_id if file_msg else None}"
                                )

                    # === DEBUG MODE: Send comparison ===
                    if settings.llm_debug_mode:
                        try:
                            debug_message = (
                                "🔍 <b>Сравнение (LLM_DEBUG_MODE=true)</b>\n\n"
                                f"📝 <b>Черновик ({result.model_name}):</b>\n"
                                f"<code>{draft_text}</code>\n\n"
                                f"✨ <b>После LLM ({settings.llm_model}):</b>\n"
                                f"<code>{refined_text}</code>"
                            )
                            # Split if too long (Telegram limit is 4096 chars)
                            if len(debug_message) > 4000:
                                debug_message = (
                                    "🔍 <b>Сравнение (LLM_DEBUG_MODE=true)</b>\n\n"
                                    f"📝 <b>Черновик:</b> {len(draft_text)} символов\n"
                                    f"<code>{draft_text[:1500]}...</code>\n\n"
                                    f"✨ <b>После LLM:</b> {len(refined_text)} символов\n"
                                    f"<code>{refined_text[:1500]}...</code>\n\n"
                                    f"ℹ️ Тексты слишком длинные, показаны первые 1500 символов"
                                )
                            await request.user_message.reply_text(debug_message, parse_mode="HTML")
                        except Exception as e:
                            logger.warning(f"Failed to send LLM debug comparison: {e}")

                except Exception as e:
                    logger.error(f"LLM refinement failed: {e}")
                    # Fallback: draft already visible, just notify completion
                    if request.draft_messages:
                        # Draft is in multiple messages, send final message
                        await request.user_message.reply_text(
                            "✅ Готово\n\nℹ️ (улучшение текста недоступно)"
                        )
                    else:
                        # Draft is in status_message, update it
                        try:
                            await request.status_message.edit_text(
                                f"✅ Готово:\n\n{draft_text}\n\nℹ️ (улучшение текста недоступно)"
                            )
                        except Exception:
                            pass
                    final_text = draft_text

            else:
                # === Direct result (short audio or non-hybrid) ===
                # Delete status message
                try:
                    await request.status_message.delete()
                except Exception as e:
                    logger.warning(f"Failed to delete status message: {e}")

                # Create keyboard
                keyboard = await self._create_interactive_state_and_keyboard(
                    usage_id=request.usage_id,
                    message_id=0,  # Will be updated after sending
                    chat_id=request.user_message.chat_id,
                    result=result,
                    final_text=result.text,
                )

                # Send result (as text or file based on length)
                main_msg, file_msg = await self._send_transcription_result(
                    request=request,
                    text=result.text,
                    keyboard=keyboard,
                    usage_id=request.usage_id,
                    prefix="✅ Готово!\n\n",
                )

                # Update state with correct message IDs
                if keyboard:
                    async with get_session() as session:
                        state_repo = TranscriptionStateRepository(session)
                        state = await state_repo.get_by_usage_id(request.usage_id)
                        if state:
                            state.message_id = main_msg.message_id
                            state.is_file_message = file_msg is not None
                            state.file_message_id = file_msg.message_id if file_msg else None
                            await state_repo.update(state)
                            logger.debug(
                                f"Updated state: message_id={main_msg.message_id}, "
                                f"is_file={file_msg is not None}, "
                                f"file_msg_id={file_msg.message_id if file_msg else None}"
                            )

            # === STAGE 3: Update database with Whisper results ===
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=request.usage_id,
                    model_size=result.model_name,
                    processing_time_seconds=result.processing_time,
                    transcription_length=len(final_text),
                    llm_model=(
                        settings.llm_model if (needs_refinement and self.llm_service) else None
                    ),
                )

            # Cleanup temporary files (both original and preprocessed)
            self.audio_handler.cleanup_file(request.file_path)
            if processed_path != request.file_path:
                self.audio_handler.cleanup_file(processed_path)

            logger.info(
                f"Request {request.id} completed successfully "
                f"(duration={request.duration_seconds}s, processing_time={result.processing_time:.2f}s)"
            )

            return result

        except Exception as e:
            # Stop progress on error
            await progress.stop()

            # Notify user of error
            try:
                await request.status_message.edit_text(
                    "❌ Произошла ошибка при обработке. Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                pass

            # Cleanup files
            self.audio_handler.cleanup_file(request.file_path)
            if processed_path != request.file_path:
                self.audio_handler.cleanup_file(processed_path)

            logger.error(f"Request {request.id} failed: {e}", exc_info=True)
            raise

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

        # Try to notify user if possible
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
            )
