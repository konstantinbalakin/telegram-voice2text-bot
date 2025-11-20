"""Telegram bot handlers for voice message processing."""

import asyncio
import logging
import uuid
from datetime import timedelta
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from src.config import settings
from src.storage.database import get_session
from src.storage.repositories import UserRepository, UsageRepository
from src.transcription.routing.router import TranscriptionRouter
from src.transcription.routing.strategies import HybridStrategy
from src.transcription.audio_handler import AudioHandler
from src.transcription.models import TranscriptionContext, TranscriptionResult
from src.services.queue_manager import QueueManager, TranscriptionRequest
from src.services.progress_tracker import ProgressTracker
from src.services.llm_service import LLMService

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


class BotHandlers:
    """Telegram bot handlers for processing voice messages with queue management."""

    def __init__(
        self,
        whisper_service: TranscriptionRouter,
        audio_handler: AudioHandler,
        queue_manager: QueueManager,
        llm_service: Optional[LLMService] = None,
    ):
        """Initialize bot handlers.

        Args:
            whisper_service: Transcription router for transcription
            audio_handler: Audio handler for file operations
            queue_manager: Queue manager for request handling
            llm_service: Optional LLM service for text refinement
        """
        self.transcription_router = whisper_service
        self.audio_handler = audio_handler
        self.queue_manager = queue_manager
        self.llm_service = llm_service

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

        # Register or get existing user from database
        async with get_session() as session:
            user_repo = UserRepository(session)

            # Check if user exists
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                # Create new user
                await user_repo.create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )

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
        if queue_depth >= settings.max_queue_size:
            await update.message.reply_text(
                "⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут.\n\n"
                f"В очереди сейчас: {queue_depth} запросов"
            )
            logger.warning(
                f"User {user.id} rejected: queue full ({queue_depth}/{settings.max_queue_size})"
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

            # Download voice file
            voice_file = await context.bot.get_file(voice.file_id)
            file_path = await self.audio_handler.download_voice_message(voice_file, voice.file_id)
            logger.info(f"File downloaded: {file_path}")

            # STAGE 2: Update with duration after download
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=usage.id,
                    voice_duration_seconds=duration_seconds,
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

                # Enqueue request
                try:
                    queue_position = await self.queue_manager.enqueue(request)
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
        if queue_depth >= settings.max_queue_size:
            await update.message.reply_text(
                "⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут.\n\n"
                f"В очереди сейчас: {queue_depth} запросов"
            )
            logger.warning(
                f"User {user.id} rejected: queue full ({queue_depth}/{settings.max_queue_size})"
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

            # Download audio file
            audio_file = await context.bot.get_file(audio.file_id)
            file_path = await self.audio_handler.download_voice_message(audio_file, audio.file_id)
            logger.info(f"File downloaded: {file_path}")

            # STAGE 2: Update with duration after download
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=usage.id,
                    voice_duration_seconds=duration_seconds,
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

                # Enqueue request
                try:
                    queue_position = await self.queue_manager.enqueue(request)
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

        except Exception as e:
            logger.error(f"Error handling audio file: {e}", exc_info=True)
            try:
                await status_msg.edit_text(
                    "❌ Произошла ошибка при обработке аудиофайла. "
                    "Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                pass

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

        # Update status message
        try:
            await request.status_message.edit_text("⚙️ Начинаю обработку...")
        except Exception as e:
            logger.warning(f"Failed to update status message: {e}")

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
            is_hybrid = isinstance(self.transcription_router.strategy, HybridStrategy)
            needs_refinement = (
                is_hybrid
                and self.transcription_router.strategy.requires_refinement(
                    request.duration_seconds
                )
            )

            final_text = result.text

            if needs_refinement and self.llm_service:
                # === STAGE 1: Send draft ===
                draft_text = result.text
                try:
                    await request.status_message.edit_text(
                        f"✅ Черновик готов:\n\n{draft_text}\n\n🔄 Улучшаю текст..."
                    )
                except Exception as e:
                    logger.warning(f"Failed to send draft message: {e}")

                # === STAGE 2: Refine with LLM ===
                try:
                    refined_text = await self.llm_service.refine_transcription(draft_text)

                    # === STAGE 3: Send final refined text ===
                    final_text = refined_text

                    # Split if needed
                    text_chunks = split_text(refined_text)

                    if len(text_chunks) == 1:
                        await request.status_message.edit_text(f"✨ Готово!\n\n{refined_text}")
                    else:
                        # Delete status message and send in chunks
                        try:
                            await request.status_message.delete()
                        except Exception as e:
                            logger.warning(f"Failed to delete status message: {e}")

                        for i, chunk in enumerate(text_chunks, 1):
                            prefix = "✨ Готово!\n\n" if i == 1 else ""
                            header = (
                                f"📝 Часть {i}/{len(text_chunks)}\n\n"
                                if len(text_chunks) > 1
                                else ""
                            )
                            await request.user_message.reply_text(prefix + header + chunk)
                            if i < len(text_chunks):
                                await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(f"LLM refinement failed: {e}")
                    # Fallback: draft is final
                    try:
                        await request.status_message.edit_text(
                            f"✅ Готово:\n\n{draft_text}\n\nℹ️ (улучшение текста недоступно)"
                        )
                    except Exception:
                        pass
                    final_text = draft_text

            else:
                # === Direct result (short audio or non-hybrid) ===
                text_chunks = split_text(result.text)

                if len(text_chunks) == 1:
                    await request.status_message.edit_text(f"✅ Готово!\n\n{result.text}")
                else:
                    # Multiple messages needed
                    try:
                        await request.status_message.delete()
                    except Exception as e:
                        logger.warning(f"Failed to delete status message: {e}")

                    for i, chunk in enumerate(text_chunks, 1):
                        prefix = "✅ Готово!\n\n" if i == 1 else ""
                        header = (
                            f"📝 Часть {i}/{len(text_chunks)}\n\n"
                            if len(text_chunks) > 1
                            else ""
                        )
                        await request.user_message.reply_text(prefix + header + chunk)
                        if i < len(text_chunks):
                            await asyncio.sleep(0.1)

            # === Update database with final text ===
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=request.usage_id,
                    model_size=result.model_name,
                    processing_time_seconds=result.processing_time,
                    transcription_length=len(final_text),
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
