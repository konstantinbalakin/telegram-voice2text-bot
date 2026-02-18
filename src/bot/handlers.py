"""Telegram bot handlers for voice message processing."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from src.config import settings, SUPPORTED_AUDIO_MIMES
from src.storage.database import get_session
from src.storage.models import User
from src.storage.repositories import (
    UserRepository,
    UsageRepository,
)
from src.transcription.routing.router import TranscriptionRouter
from src.transcription.audio_handler import AudioHandler
from src.transcription.models import TranscriptionContext
from src.services.queue_manager import QueueManager, TranscriptionRequest
from src.services.telegram_client import TelegramClientService

if TYPE_CHECKING:
    from src.services.transcription_orchestrator import TranscriptionOrchestrator

logger = logging.getLogger(__name__)

# Telegram message length limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# Telegram Client API file size limit (2 GB)
TELEGRAM_CLIENT_API_MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024


@dataclass
class MediaInfo:
    """Extracted media information from a Telegram message."""

    file_id: str
    file_size: int
    duration_seconds: int | None  # None for document (ffprobe later)
    media_type: str  # "voice", "audio", "document", "video"
    mime_type: str | None = None  # Only for document
    file_name: str | None = None


def format_wait_time(seconds: float) -> str:
    """Format wait time for user display."""
    if seconds < 60:
        return f"~{int(seconds)}с"
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    if secs > 0:
        return f"~{minutes}м {secs}с"
    return f"~{minutes}м"


def split_text(
    text: str,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
    header_reserve: int = 50,
) -> list[str]:
    """Split text into chunks that fit Telegram message length limit.

    Args:
        text: Text to split
        max_length: Maximum length of each chunk (default: 4096)
        header_reserve: Reserve space for header

    Returns:
        List of text chunks
    """
    effective_max = max_length - header_reserve

    if len(text) <= max_length:
        return [text]

    chunks = []

    while text:
        if len(text) <= effective_max:
            chunks.append(text)
            break

        chunk = text[:effective_max]

        split_pos = chunk.rfind("\n\n")
        if split_pos > effective_max * 0.5:
            chunks.append(text[:split_pos])
            text = text[split_pos + 2 :]
            continue

        split_pos = chunk.rfind("\n")
        if split_pos > effective_max * 0.5:
            chunks.append(text[:split_pos])
            text = text[split_pos + 1 :]
            continue

        split_pos = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
        if split_pos > effective_max * 0.5:
            chunks.append(text[: split_pos + 1])
            text = text[split_pos + 2 :]
            continue

        split_pos = chunk.rfind(" ")
        if split_pos > 0:
            chunks.append(text[:split_pos])
            text = text[split_pos + 1 :]
            continue

        chunks.append(text[:effective_max])
        text = text[effective_max:]

    return chunks


class BotHandlers:
    """Telegram bot handlers for processing voice messages with queue management."""

    def __init__(
        self,
        transcription_router: TranscriptionRouter,
        audio_handler: AudioHandler,
        queue_manager: QueueManager,
        orchestrator: "TranscriptionOrchestrator",
        telegram_client: Optional[TelegramClientService] = None,
    ):
        """Initialize bot handlers.

        Args:
            transcription_router: Transcription router for transcription
            audio_handler: Audio handler for file operations
            queue_manager: Queue manager for request handling
            orchestrator: Transcription orchestrator for processing pipeline
            telegram_client: Optional Telegram Client API service for large files
        """
        self.transcription_router = transcription_router
        self.audio_handler = audio_handler
        self.queue_manager = queue_manager
        self.orchestrator = orchestrator
        self.telegram_client = telegram_client

        # Register callback for queue updates
        self.queue_manager.set_on_queue_changed(self._update_queue_messages)

        # Start queue worker
        asyncio.create_task(
            self.queue_manager.start_worker(self.orchestrator.process_transcription)
        )

    def _check_quota(self, user: User, duration: int) -> tuple[bool, str]:
        """Check if user has enough daily quota for the transcription.

        Args:
            user: Database user object
            duration: Audio duration in seconds

        Returns:
            Tuple of (allowed, message). If allowed is False, message contains
            the rejection reason to send to the user.
        """
        if not settings.enable_quota_check:
            return (True, "")

        if user.is_unlimited:
            return (True, "")

        # Reset daily usage if last_reset_date is not today
        today = date.today()
        if user.last_reset_date != today:
            user.today_usage_seconds = 0
            user.last_reset_date = today

        remaining = user.daily_quota_seconds - user.today_usage_seconds
        if user.today_usage_seconds + duration > user.daily_quota_seconds:
            return (
                False,
                f"⚠️ Достигнут дневной лимит ({user.daily_quota_seconds} сек).\n\n"
                f"Использовано: {user.today_usage_seconds} сек\n"
                f"Остаток: {max(0, remaining)} сек\n"
                f"Запрошено: {duration} сек\n\n"
                f"Лимит сбросится завтра.",
            )

        return (True, "")

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
                wait_str = format_wait_time(wait_time)
                proc_str = format_wait_time(processing_time)

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

        async with get_session() as session:
            user_repo = UserRepository(session)

            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                logger.debug(f"Creating new user: telegram_id={user.id}")
                await user_repo.create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
            else:
                logger.debug(f"Existing user: id={db_user.id}, telegram_id={user.id}")

        welcome_message = (
            "Привет \U0001F44B\n\n"
            "Я *Voice2Text*\\. Помогаю не переслушивать голосовые по десять раз\\.\n\n"
            "Просто пришли аудио — я:\n\n"
            "\\- аккуратно расшифрую текст\n"
            "\\- расставлю знаки препинания\n"
            "\\- приведу всё в читабельный вид\n"
            "\\- сделаю красиво \\(моя фишка \U0001F60A\\)\n\n\n"
            "Поддерживаю длинные файлы до 3 часов\\.\n"
            "Сейчас всё *бесплатно*\\.\n\n"
            "Можем начинать \U0001F642\n\n"
            "Жду твоё первое голосовое \U0001F399\n"
            "\U0001F447\U0001F447\U0001F447"
        )

        if update.message:
            await update.message.reply_text(welcome_message, parse_mode="MarkdownV2")
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

            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                if update.message:
                    await update.message.reply_text("Пользователь не найден. Используйте /start")
                return

            total_count = await usage_repo.count_by_user_id(db_user.id)

            if total_count == 0:
                if update.message:
                    await update.message.reply_text(
                        "У вас пока нет обработанных голосовых сообщений.\n"
                        "Отправьте голосовое сообщение, чтобы начать!"
                    )
                return

            total_duration = await usage_repo.get_user_total_duration(db_user.id)
            avg_duration = total_duration / total_count

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

    def _extract_media_info(self, update: Update, media_type: str) -> MediaInfo | None:
        """Extract media information from a Telegram message.

        Args:
            update: Telegram update object
            media_type: Type of media ("voice", "audio", "document", "video")

        Returns:
            MediaInfo or None if media not found in the message
        """
        if not update.message:
            return None

        media_obj = getattr(update.message, media_type, None)
        if not media_obj:
            return None

        # Convert duration to int (handling timedelta vs int)
        duration_seconds: int | None = None
        if media_type != "document":
            raw_duration = getattr(media_obj, "duration", None)
            if raw_duration:
                if isinstance(raw_duration, timedelta):
                    duration_seconds = int(raw_duration.total_seconds())
                else:
                    duration_seconds = int(raw_duration)
            else:
                duration_seconds = 0

        return MediaInfo(
            file_id=media_obj.file_id,
            file_size=media_obj.file_size or 0,
            duration_seconds=duration_seconds,
            media_type=media_type,
            mime_type=(getattr(media_obj, "mime_type", None) if media_type == "document" else None),
            file_name=getattr(media_obj, "file_name", None),
        )

    async def _handle_media_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        media_info: MediaInfo,
    ) -> None:
        """Unified handler for all media types (voice, audio, document, video).

        Args:
            update: Telegram update object
            context: Telegram context object
            media_info: Extracted media information
        """
        user = update.effective_user
        if not user or not update.message:
            return

        logger.debug(
            f"_handle_media_message: user_id={user.id}, type={media_info.media_type}, "
            f"file_id={media_info.file_id}, duration={media_info.duration_seconds}s, "
            f"file_size={media_info.file_size}"
        )

        # Document: MIME check at start
        if media_info.media_type == "document":
            mime_type = media_info.mime_type or ""
            if mime_type not in SUPPORTED_AUDIO_MIMES:
                logger.debug(f"Document ignored: unsupported MIME type {mime_type}")
                return

        # 1. VALIDATE DURATION (skip for document — no duration metadata)
        if media_info.duration_seconds is not None:
            if media_info.duration_seconds > settings.max_voice_duration_seconds:
                max_dur = settings.max_voice_duration_seconds
                dur = media_info.duration_seconds
                await update.message.reply_text(
                    f"⚠️ Максимальная длительность: {max_dur // 60} мин\n\n"
                    f"Ваш файл: {dur // 60} мин {dur % 60} сек"
                )
                logger.warning(f"User {user.id} rejected: duration {dur}s > {max_dur}s")
                return

        # 2. CHECK QUEUE CAPACITY
        queue_depth = self.queue_manager.get_queue_depth()
        if queue_depth >= settings.max_queue_size:
            await update.message.reply_text(
                "⚠️ Очередь переполнена. Пожалуйста, попробуйте через несколько минут.\n\n"
                f"В очереди сейчас: {queue_depth} запросов"
            )
            logger.warning(
                f"User {user.id} rejected: queue full " f"({queue_depth}/{settings.max_queue_size})"
            )
            return

        # 3. CHECK FILE SIZE
        if media_info.file_size:
            if settings.telethon_enabled and self.telegram_client:
                max_size = TELEGRAM_CLIENT_API_MAX_FILE_SIZE
            else:
                max_size = settings.max_file_size_bytes

            if media_info.file_size > max_size:
                max_size_mb = max_size / 1024 / 1024
                file_size_mb = media_info.file_size / 1024 / 1024
                await update.message.reply_text(
                    f"⚠️ Файл слишком большой для обработки.\n\n"
                    f"Максимальный размер: {max_size_mb:.0f} МБ\n"
                    f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                    "Пожалуйста, отправьте файл меньшего размера."
                )
                logger.warning(
                    f"User {user.id} sent {media_info.media_type} too large: "
                    f"{file_size_mb:.1f} MB (max: {max_size_mb:.0f} MB)"
                )
                return

        # 4. CHECK QUOTA (skip for document — duration unknown until ffprobe)
        if media_info.duration_seconds is not None:
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
                quota_ok, quota_msg = self._check_quota(db_user, media_info.duration_seconds)
                if not quota_ok:
                    await update.message.reply_text(quota_msg)
                    logger.warning(f"User {user.id} rejected: quota exceeded")
                    return

        # Send initial status
        status_msg = await update.message.reply_text("📥 Загружаю файл...")

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)
                usage_repo = UsageRepository(session)

                db_user = await user_repo.get_by_telegram_id(user.id)
                if not db_user:
                    db_user = await user_repo.create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )

                usage = await usage_repo.create(
                    user_id=db_user.id,
                    voice_file_id=media_info.file_id,
                )
                logger.info(
                    f"Usage record {usage.id} created for {media_info.media_type} "
                    f"from user {user.id}"
                )

            # Download file (hybrid: Bot API for <=20MB, Client API for >20MB)
            if media_info.file_size and media_info.file_size > settings.max_file_size_bytes:
                if self.telegram_client and settings.telethon_enabled:
                    logger.info(
                        f"File size {media_info.file_size} bytes exceeds Bot API limit, "
                        f"using Client API"
                    )
                    file_path = await self.telegram_client.download_large_file(
                        message_id=update.message.message_id,
                        chat_id=update.message.chat_id,
                        output_dir=self.audio_handler.temp_dir,
                    )
                    if not file_path:
                        raise RuntimeError("Client API download returned None")
                else:
                    max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                    file_size_mb = media_info.file_size / 1024 / 1024
                    await status_msg.edit_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n"
                        f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
                        "Client API не настроен. Пожалуйста, отправьте файл меньшего размера."
                    )
                    logger.warning(f"User {user.id} sent large file but Client API unavailable")
                    return
            else:
                telegram_file = await context.bot.get_file(media_info.file_id)
                file_path = await self.audio_handler.download_voice_message(
                    telegram_file, media_info.file_id
                )

            logger.info(f"File downloaded: {file_path}")

            # Video: extract audio track and cleanup video file
            if media_info.media_type == "video":
                await status_msg.edit_text("🎵 Извлекаю аудиодорожку...")
                try:
                    video_path = file_path
                    file_path = await self.audio_handler.extract_audio_track(video_path)
                except ValueError as e:
                    await status_msg.edit_text("❌ Видео не содержит аудиодорожки.")
                    self.audio_handler.cleanup_file(video_path)
                    logger.warning(f"Video has no audio: {e}")
                    return
                self.audio_handler.cleanup_file(video_path)

            # Use the known duration or determine via ffprobe (document)
            duration_seconds = media_info.duration_seconds or 0

            # Document: get duration via ffprobe, validate, check quota
            if media_info.media_type == "document":
                ffprobe_duration = await self.audio_handler.get_audio_duration_ffprobe(file_path)
                if ffprobe_duration is not None:
                    duration_seconds = int(ffprobe_duration)
                else:
                    duration_seconds = 0

                # Validate duration after ffprobe
                if duration_seconds > settings.max_voice_duration_seconds:
                    max_dur = settings.max_voice_duration_seconds
                    await status_msg.edit_text(
                        f"⚠️ Максимальная длительность: {max_dur // 60} мин\n\n"
                        f"Ваш файл: {duration_seconds // 60} мин "
                        f"{duration_seconds % 60} сек"
                    )
                    self.audio_handler.cleanup_file(file_path)
                    return

                # Check quota after duration is known
                async with get_session() as session:
                    user_repo = UserRepository(session)
                    quota_user = await user_repo.get_by_telegram_id(user.id)
                    if quota_user:
                        quota_ok, quota_msg = self._check_quota(quota_user, duration_seconds)
                        if not quota_ok:
                            await status_msg.edit_text(quota_msg)
                            logger.warning(f"User {user.id} rejected: quota exceeded")
                            self.audio_handler.cleanup_file(file_path)
                            return

            # Update usage with duration
            async with get_session() as session:
                usage_repo = UsageRepository(session)
                await usage_repo.update(
                    usage_id=usage.id,
                    voice_duration_seconds=duration_seconds,
                )
                logger.info(
                    f"Usage record {usage.id} updated with duration " f"{duration_seconds}s"
                )

            # Create transcription context
            transcription_context = TranscriptionContext(
                user_id=user.id,
                duration_seconds=duration_seconds,
                file_size_bytes=media_info.file_size,
                language="ru",
            )

            # Benchmark mode (voice/audio only)
            if (
                media_info.media_type in ("voice", "audio")
                and self.transcription_router.strategy.is_benchmark_mode()
            ):
                logger.info(f"Running benchmark on {media_info.media_type}...")
                report = await self.transcription_router.run_benchmark(
                    file_path, transcription_context
                )

                successful_results = [r for r in report.results if r.error is None]
                if successful_results:
                    best_result = report.get_sorted_by_speed()[0]
                    async with get_session() as session:
                        usage_repo = UsageRepository(session)
                        await usage_repo.create(
                            user_id=db_user.id,
                            voice_duration_seconds=duration_seconds,
                            voice_file_id=media_info.file_id,
                            transcription_length=len(best_result.text),
                            model_size=best_result.model_name,
                            processing_time_seconds=best_result.processing_time,
                        )

                self.audio_handler.cleanup_file(file_path)

                report_text = report.to_markdown()
                if len(report_text) <= TELEGRAM_MAX_MESSAGE_LENGTH:
                    await status_msg.edit_text(report_text, parse_mode="Markdown")
                else:
                    if successful_results:
                        best_result = report.get_sorted_by_speed()[0]
                        await status_msg.edit_text(
                            f"✅ Benchmark завершен!\n\n"
                            f"Лучший результат: "
                            f"{best_result.config.display_name if best_result.config else best_result.provider_used}\n"
                            f"Скорость: {best_result.processing_time:.2f}s "
                            f"(RTF: {best_result.realtime_factor:.2f}x)\n\n"
                            f"Транскрипция:\n{best_result.text}"
                        )
                    else:
                        await status_msg.edit_text("❌ Все модели не смогли обработать аудио")

                    chunks = [
                        report_text[i : i + TELEGRAM_MAX_MESSAGE_LENGTH]
                        for i in range(
                            0,
                            len(report_text),
                            TELEGRAM_MAX_MESSAGE_LENGTH,
                        )
                    ]
                    for chunk in chunks:
                        await update.message.reply_text(chunk, parse_mode="MarkdownV2")

                logger.info(f"Benchmark completed for user {user.id}")
                return

            # Normal transcription mode with queue
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
                f"Transcription request created: id={request.id}, "
                f"user_id={user.id}, "
                f"duration={duration_seconds}s, file_path={file_path}"
            )

            try:
                queue_position = await self.queue_manager.enqueue(request)
                logger.debug(f"Request enqueued: id={request.id}, " f"position={queue_position}")
                active_workers = self.queue_manager.get_processing_count()

                if queue_position > 1 or active_workers > 0:
                    actual_position = self.queue_manager.get_queue_position_by_id(request.id)
                    wait_time, processing_time = self.queue_manager.get_estimated_wait_time_by_id(
                        request.id, settings.progress_rtf
                    )

                    wait_str = format_wait_time(wait_time)
                    proc_str = format_wait_time(processing_time)

                    await status_msg.edit_text(
                        f"📋 В очереди: позиция {actual_position}\n"
                        f"⏱️ Ожидание в очереди: {wait_str}\n"
                        f"🎯 Обработка вашего сообщения: {proc_str}"
                    )
                    logger.info(f"Request {request.id} enqueued at position " f"{actual_position}")
                else:
                    await status_msg.edit_text("⚙️ Начинаю обработку...")
                    logger.info(f"Request {request.id} starting immediately")

            except asyncio.QueueFull:
                await status_msg.edit_text("⚠️ Очередь переполнена. Пожалуйста, попробуйте позже.")
                self.audio_handler.cleanup_file(file_path)
                return

        except BadRequest as e:
            if "File is too big" in str(e):
                max_size_mb = settings.max_file_size_bytes / 1024 / 1024
                logger.warning(
                    f"User {user.id} {media_info.media_type} file too big " f"for Telegram API: {e}"
                )
                try:
                    await status_msg.edit_text(
                        "⚠️ Файл слишком большой для обработки.\n\n"
                        f"Максимальный размер: {max_size_mb:.0f} МБ\n\n"
                        "Пожалуйста, отправьте файл меньшего размера."
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
            logger.error(
                f"Error handling {media_info.media_type} message: {e}",
                exc_info=True,
            )
            try:
                await status_msg.edit_text(
                    "❌ Произошла ошибка при обработке файла. " "Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                pass

    async def voice_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle voice messages."""
        media_info = self._extract_media_info(update, "voice")
        if media_info:
            await self._handle_media_message(update, context, media_info)

    async def audio_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle audio file messages."""
        media_info = self._extract_media_info(update, "audio")
        if media_info:
            await self._handle_media_message(update, context, media_info)

    async def document_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle document messages with audio MIME types."""
        media_info = self._extract_media_info(update, "document")
        if media_info:
            await self._handle_media_message(update, context, media_info)

    async def video_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle video messages by extracting audio track."""
        media_info = self._extract_media_info(update, "video")
        if media_info:
            await self._handle_media_message(update, context, media_info)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        logger.error(
            f"Exception while handling an update: {context.error}",
            exc_info=context.error,
        )

        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
            )
