"""Telegram bot handlers for voice message processing."""
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from src.storage.database import get_session
from src.storage.repositories import UserRepository, UsageRepository
from src.transcription.whisper_service import WhisperService
from src.transcription.audio_handler import AudioHandler

logger = logging.getLogger(__name__)


class BotHandlers:
    """Telegram bot handlers for processing voice messages."""

    def __init__(
        self,
        whisper_service: WhisperService,
        audio_handler: AudioHandler,
    ):
        """Initialize bot handlers.

        Args:
            whisper_service: Whisper service for transcription
            audio_handler: Audio handler for file operations
        """
        self.whisper_service = whisper_service
        self.audio_handler = audio_handler

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
        """Handle voice messages.

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

        # Send processing message
        processing_msg = await update.message.reply_text(
            "Обрабатываю голосовое сообщение..."
        )

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)
                usage_repo = UsageRepository(session)

                # Get user from database
                db_user = await user_repo.get_by_telegram_id(user.id)
                if not db_user:
                    # Create user if not exists
                    db_user = await user_repo.create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )

                # Download voice file
                voice_file = await context.bot.get_file(voice.file_id)
                file_path = await self.audio_handler.download_voice_message(
                    voice_file, voice.file_id
                )

                # Transcribe
                transcription_text, processing_time = await self.whisper_service.transcribe(file_path)

                # Convert duration to int
                duration_seconds = 0
                if voice.duration:
                    if isinstance(voice.duration, timedelta):
                        duration_seconds = int(voice.duration.total_seconds())
                    else:
                        duration_seconds = int(voice.duration)

                # Save to database
                await usage_repo.create(
                    user_id=db_user.id,
                    voice_duration_seconds=duration_seconds,
                    voice_file_id=voice.file_id,
                    transcription_text=transcription_text,
                    model_size=self.whisper_service.model_size,
                    processing_time_seconds=processing_time,
                )

                # Clean up files
                self.audio_handler.cleanup_file(file_path)

                # Send transcription
                await processing_msg.edit_text(
                    f"Расшифровка:\n\n{transcription_text}"
                )

                logger.info(
                    f"Successfully transcribed voice message for user {user.id}, "
                    f"duration: {voice.duration}s"
                )

        except Exception as e:
            logger.error(f"Error processing voice message: {e}", exc_info=True)
            await processing_msg.edit_text(
                "Произошла ошибка при обработке голосового сообщения. "
                "Пожалуйста, попробуйте еще раз."
            )

    async def audio_message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle audio file messages.

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

        # Send processing message
        processing_msg = await update.message.reply_text(
            "Обрабатываю аудиофайл..."
        )

        try:
            async with get_session() as session:
                user_repo = UserRepository(session)
                usage_repo = UsageRepository(session)

                # Get user from database
                db_user = await user_repo.get_by_telegram_id(user.id)
                if not db_user:
                    # Create user if not exists
                    db_user = await user_repo.create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                    )

                # Download audio file
                audio_file = await context.bot.get_file(audio.file_id)
                file_path = await self.audio_handler.download_voice_message(
                    audio_file, audio.file_id
                )

                # Transcribe
                transcription_text, processing_time = await self.whisper_service.transcribe(file_path)

                # Convert duration to int
                duration_seconds = 0
                if audio.duration:
                    if isinstance(audio.duration, timedelta):
                        duration_seconds = int(audio.duration.total_seconds())
                    else:
                        duration_seconds = int(audio.duration)

                # Save to database
                await usage_repo.create(
                    user_id=db_user.id,
                    voice_duration_seconds=duration_seconds,
                    voice_file_id=audio.file_id,
                    transcription_text=transcription_text,
                    model_size=self.whisper_service.model_size,
                    processing_time_seconds=processing_time,
                )

                # Clean up files
                self.audio_handler.cleanup_file(file_path)

                # Send transcription
                await processing_msg.edit_text(
                    f"Расшифровка:\n\n{transcription_text}"
                )

                logger.info(
                    f"Successfully transcribed audio file for user {user.id}, "
                    f"duration: {audio.duration}s"
                )

        except Exception as e:
            logger.error(f"Error processing audio file: {e}", exc_info=True)
            await processing_msg.edit_text(
                "Произошла ошибка при обработке аудиофайла. "
                "Пожалуйста, попробуйте еще раз."
            )

    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
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
