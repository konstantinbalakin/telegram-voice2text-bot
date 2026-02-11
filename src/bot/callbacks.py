"""Callback query handlers for interactive transcription."""

import logging
import time
from typing import Optional, cast, TYPE_CHECKING
from telegram import Update, Message, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes
from src.services.pdf_generator import create_file_object

from src.bot.keyboards import decode_callback_data, create_transcription_keyboard
from src.storage.models import TranscriptionState
from src.storage.repositories import (
    TranscriptionStateRepository,
    TranscriptionVariantRepository,
    TranscriptionSegmentRepository,
    UsageRepository,
    UserRepository,
)
from src.services.text_processor import TextProcessor
from src.services.progress_tracker import ProgressTracker
from src.config import settings
from src.bot.retranscribe_handlers import handle_retranscribe_menu, handle_retranscribe
from src.utils.html_utils import sanitize_html

if TYPE_CHECKING:
    from src.bot.handlers import BotHandlers

logger = logging.getLogger(__name__)


# Phase 3: Length level transitions
# Format: current_level -> {direction: next_level}
LEVEL_TRANSITIONS = {
    "default": {"shorter": "short", "longer": "long"},
    "short": {"shorter": "shorter", "longer": "default"},
    "shorter": {"longer": "short"},  # No further shorter
    "long": {"shorter": "default", "longer": "longer"},
    "longer": {"shorter": "long"},  # No further longer
}


class CallbackHandlers:
    """Handler for callback queries from inline keyboards."""

    def __init__(
        self,
        state_repo: TranscriptionStateRepository,
        variant_repo: TranscriptionVariantRepository,
        segment_repo: TranscriptionSegmentRepository,
        usage_repo: "UsageRepository",
        text_processor: Optional[TextProcessor] = None,
        bot_handlers: Optional["BotHandlers"] = None,
        user_repo: Optional["UserRepository"] = None,
    ):
        """
        Initialize callback handlers.

        Args:
            state_repo: Repository for transcription states
            variant_repo: Repository for transcription variants
            segment_repo: Repository for transcription segments
            usage_repo: Repository for usage records
            text_processor: Text processor for LLM operations (optional)
            bot_handlers: BotHandlers instance for retranscription (optional, Phase 8)
            user_repo: Repository for user records (optional, for ownership checks)
        """
        self.state_repo = state_repo
        self.variant_repo = variant_repo
        self.segment_repo = segment_repo
        self.usage_repo = usage_repo
        self.text_processor = text_processor
        self.bot_handlers = bot_handlers
        self.user_repo = user_repo

    async def _check_variant_limit(self, usage_id: int) -> bool:
        """Check if the variant limit for a transcription has been reached.

        Returns:
            True if the limit has been reached, False otherwise.
        """
        count = await self.variant_repo.count_by_usage_id(usage_id)
        if count >= settings.max_cached_variants_per_transcription:
            logger.warning(
                f"Variant limit reached: usage_id={usage_id}, count={count}, "
                f"limit={settings.max_cached_variants_per_transcription}"
            )
            return True
        return False

    async def update_transcription_display(
        self,
        query: CallbackQuery,
        context: ContextTypes.DEFAULT_TYPE,
        state: TranscriptionState,
        new_text: str,
        keyboard: InlineKeyboardMarkup | None,
        state_repo: TranscriptionStateRepository,
    ) -> None:
        """Update transcription display (text or file) based on state and length.

        Args:
            query: Callback query
            context: Bot context
            state: TranscriptionState
            new_text: New text content
            keyboard: New inline keyboard markup
            state_repo: Repository for updating state (no nested sessions)
        """
        # Get user-specific file number for filename generation
        usage = await self.usage_repo.get_by_id(state.usage_id)
        if usage:
            file_number = await self.usage_repo.count_by_user_id(usage.user_id)
        else:
            # Fallback to usage_id if usage not found (shouldn't happen)
            file_number = state.usage_id
            logger.warning(f"Usage {state.usage_id} not found, using usage_id as file_number")

        # Sanitize HTML before sending to Telegram (LLM may produce unsupported tags)
        new_text = sanitize_html(new_text)

        if not state.is_file_message and len(new_text) <= settings.file_threshold_chars:
            # Simple case: text message, stays text message
            await query.edit_message_text(new_text, reply_markup=keyboard, parse_mode="HTML")
            logger.debug(f"Updated text message: usage_id={state.usage_id}")

        elif state.is_file_message and len(new_text) > settings.file_threshold_chars:
            # File message, stays file message
            message = cast(Message, query.message)
            chat_id = message.chat_id

            # Get mode label
            mode_labels = {
                "original": "Исходный текст",
                "structured": "Структурированный",
                "summary": "Резюме",
                "magic": "Красиво",
            }
            mode_label = mode_labels.get(state.active_mode, state.active_mode)

            # Update main message with keyboard
            await query.edit_message_text(
                f"📝 Транскрипция готова! Файл ниже ↓\n\nРежим: {mode_label}",
                reply_markup=keyboard,
                parse_mode="HTML",
            )

            # Delete old file
            if state.file_message_id:
                try:
                    await context.bot.delete_message(chat_id, state.file_message_id)
                    logger.debug(f"Deleted old file: message_id={state.file_message_id}")
                except Exception as e:
                    logger.warning(f"Could not delete old file: {e}")

            # Send new file (PDF if possible, fallback to TXT)
            file_obj, file_extension = create_file_object(
                new_text, f"{file_number}_{state.active_mode}"
            )

            new_file_msg = await context.bot.send_document(
                chat_id=chat_id,
                document=file_obj,
                filename=file_obj.name,
                caption=f"📄 {mode_label} ({len(new_text)} символов, {file_extension})",
                parse_mode="HTML",
            )

            # Update state with new file_message_id
            state.file_message_id = new_file_msg.message_id
            await state_repo.update(state)

            logger.debug(
                f"Updated file message: usage_id={state.usage_id}, "
                f"new_file_msg_id={new_file_msg.message_id}"
            )

        elif not state.is_file_message and len(new_text) > settings.file_threshold_chars:
            # Text message → needs to become file message
            message = cast(Message, query.message)
            chat_id = message.chat_id

            mode_labels = {
                "original": "Исходный текст",
                "structured": "Структурированный",
                "summary": "Резюме",
                "magic": "Красиво",
            }
            mode_label = mode_labels.get(state.active_mode, state.active_mode)

            # Update existing message to info message
            await query.edit_message_text(
                f"📝 Транскрипция готова! Файл ниже ↓\n\nРежим: {mode_label}",
                reply_markup=keyboard,
                parse_mode="HTML",
            )

            # Send file (PDF if possible, fallback to TXT)
            file_obj, file_extension = create_file_object(
                new_text, f"{file_number}_{state.active_mode}"
            )

            file_msg = await context.bot.send_document(
                chat_id=chat_id,
                document=file_obj,
                filename=file_obj.name,
                caption=f"📄 {mode_label} ({len(new_text)} символов, {file_extension})",
                parse_mode="HTML",
            )

            # Update state: now it's a file message
            state.is_file_message = True
            state.file_message_id = file_msg.message_id
            await state_repo.update(state)

            logger.debug(
                f"Converted text to file: usage_id={state.usage_id}, file_msg_id={file_msg.message_id}"
            )

        else:
            # File message → becomes text message (rare, but possible)
            # Delete file
            message = cast(Message, query.message)
            if state.file_message_id:
                try:
                    await context.bot.delete_message(message.chat_id, state.file_message_id)
                    logger.debug(f"Deleted file: message_id={state.file_message_id}")
                except Exception as e:
                    logger.warning(f"Could not delete file: {e}")

            # Update main message with text
            await query.edit_message_text(new_text, reply_markup=keyboard, parse_mode="HTML")

            # Update state: no longer file message
            state.is_file_message = False
            state.file_message_id = None
            await state_repo.update(state)

            logger.debug(f"Converted file to text: usage_id={state.usage_id}")

    async def handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Route callback queries to appropriate handlers.

        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        # Acknowledge callback
        await query.answer()

        # Handle noop (non-interactive buttons)
        if query.data == "noop":
            return

        # Decode callback data
        try:
            data = decode_callback_data(query.data)
            action = data["action"]
        except Exception as e:
            logger.error(f"Failed to decode callback data '{query.data}': {e}")
            await query.answer("Ошибка обработки", show_alert=True)
            return

        # IDOR protection: verify the user pressing the button owns the transcription
        usage_id = data.get("usage_id")
        if usage_id is not None and self.user_repo:
            usage = await self.usage_repo.get_by_id(usage_id)
            if not usage:
                logger.warning(f"IDOR check: usage_id={usage_id} not found")
                await query.answer("Доступ запрещён", show_alert=True)
                return
            owner = await self.user_repo.get_by_id(usage.user_id)
            if not owner or owner.telegram_id != query.from_user.id:
                logger.warning(
                    f"IDOR blocked: user {query.from_user.id} tried to access "
                    f"usage_id={usage_id} owned by user_id={usage.user_id}"
                )
                await query.answer("Доступ запрещён", show_alert=True)
                return

        # Route to appropriate handler
        try:
            if action == "mode":
                await self.handle_mode_change(update, context)
            elif action == "length":
                await self.handle_length_change(update, context)
            elif action == "emoji":
                await self.handle_emoji_toggle(update, context)
            elif action == "timestamps":
                await self.handle_timestamps_toggle(update, context)
            elif action == "retranscribe_menu":
                await handle_retranscribe_menu(update, context)
            elif action == "retranscribe":
                if not self.bot_handlers:
                    logger.error("BotHandlers not available for retranscribe")
                    await query.answer("Ретранскрипция недоступна", show_alert=True)
                    return
                await handle_retranscribe(update, context, self.bot_handlers)
            elif action == "back":
                await self.handle_back(update, context)
            else:
                logger.warning(f"Unknown callback action: {action}")
                await query.answer("Функция пока не реализована", show_alert=True)
        except Exception as e:
            logger.error(f"Error handling callback query: {e}", exc_info=True)
            await query.answer("Произошла ошибка", show_alert=True)

    async def handle_mode_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle mode change (original/structured/summary).

        Phase 2: Implements "original" and "structured" modes.

        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        data = decode_callback_data(query.data)
        usage_id = data["usage_id"]
        new_mode = data["mode"]

        logger.info(f"Mode change request: usage_id={usage_id}, mode={new_mode}")

        # Get current state
        state = await self.state_repo.get_by_usage_id(usage_id)
        if not state:
            await query.answer("Состояние не найдено", show_alert=True)
            return

        # If already in this mode, just acknowledge
        if state.active_mode == new_mode:
            logger.debug(f"Already in {new_mode} mode for usage_id={usage_id}")
            return

        # Validate mode is supported
        if new_mode == "structured" and not settings.enable_structured_mode:
            await query.answer("Структурированный режим отключен", show_alert=True)
            return

        if new_mode == "summary" and not settings.enable_summary_mode:
            await query.answer("Режим резюме отключен", show_alert=True)
            return

        if new_mode == "magic" and not settings.enable_magic_mode:
            await query.answer("Magic режим отключен", show_alert=True)
            return

        if new_mode not in ["original", "structured", "summary", "magic"]:
            await query.answer("Функция будет доступна в следующих версиях", show_alert=True)
            return

        # Reset formatting parameters when switching modes
        # This ensures consistency: when switching modes, we start with default formatting
        # Users can then adjust emoji/length/timestamps for the new mode
        target_emoji_level = 1 if new_mode in ["structured", "magic"] else 0
        target_length_level = "default"
        target_timestamps_enabled = False

        # Get or generate variant with default parameters
        variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=new_mode,
            length_level=target_length_level,
            emoji_level=target_emoji_level,
            timestamps_enabled=target_timestamps_enabled,
        )

        if not variant:
            # Need to generate variant
            if new_mode == "structured":
                # Generate structured text
                if not self.text_processor:
                    await query.answer(
                        "Обработка текста недоступна (LLM отключен)", show_alert=True
                    )
                    return

                # Get original text
                original_variant = await self.variant_repo.get_variant(
                    usage_id=usage_id, mode="original"
                )
                if not original_variant:
                    await query.answer("Исходный текст не найден", show_alert=True)
                    return

                # Acknowledge callback immediately
                await query.answer("Начинаю обработку...")

                # Edit message to show processing started
                processing_message = "🔄 Структурирую текст, пожалуйста подождите..."
                try:
                    await query.edit_message_text(processing_message)
                except Exception as e:
                    logger.warning(f"Failed to update message to processing state: {e}")

                # Start progress tracker
                # Note: ProgressTracker expects a Message object, but we have query.message
                # We'll use estimated duration from config for LLM processing
                progress = ProgressTracker(
                    message=cast(Message, query.message),
                    duration_seconds=settings.llm_processing_duration,
                    rtf=1.0,  # For LLM, we use fixed duration, so RTF = 1.0
                    update_interval=settings.progress_update_interval,
                )
                await progress.start()

                # Generate structured text
                try:
                    start_time = time.time()

                    # Run text processing and progress tracking concurrently
                    structured_text = await self.text_processor.create_structured(
                        original_variant.text_content
                    )

                    processing_time = time.time() - start_time

                    # Stop progress tracker
                    await progress.stop()

                    # Save variant (UPSERT: handles race conditions)
                    # Check variant limit before creating
                    if await self._check_variant_limit(usage_id):
                        await query.answer("Достигнут лимит вариантов", show_alert=True)
                        return
                    variant, created = await self.variant_repo.get_or_create_variant(
                        usage_id=usage_id,
                        mode="structured",
                        text_content=structured_text,
                        length_level=target_length_level,
                        emoji_level=target_emoji_level,
                        timestamps_enabled=target_timestamps_enabled,
                        generated_by="llm",
                        llm_model=settings.llm_model,
                        processing_time_seconds=processing_time,
                    )
                    if created:
                        logger.info(
                            f"Generated structured text: usage_id={usage_id}, "
                            f"time={processing_time:.2f}s"
                        )
                    else:
                        logger.info(
                            f"Structured variant already exists: usage_id={usage_id}, "
                            "using cached version"
                        )

                except Exception as e:
                    # Stop progress tracker on error
                    await progress.stop()

                    logger.error(f"Failed to generate structured text: {e}", exc_info=True)

                    # Restore original text and show error
                    try:
                        segments = await self.segment_repo.get_by_usage_id(usage_id)
                        has_segments = len(segments) > 0
                        await query.edit_message_text(
                            sanitize_html(original_variant.text_content),
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

                    # Try to answer query (may fail if query is too old)
                    try:
                        await query.answer("Не удалось обработать текст", show_alert=True)
                    except Exception as answer_error:
                        logger.warning(f"Failed to answer callback query: {answer_error}")
                    return

            elif new_mode == "summary":
                # Generate summary text (Phase 4)
                if not self.text_processor:
                    await query.answer(
                        "Обработка текста недоступна (LLM отключен)", show_alert=True
                    )
                    return

                # Get original text
                original_variant = await self.variant_repo.get_variant(
                    usage_id=usage_id, mode="original"
                )
                if not original_variant:
                    await query.answer("Исходный текст не найден", show_alert=True)
                    return

                # Acknowledge callback immediately
                await query.answer("Начинаю создание резюме...")

                # Edit message to show processing started
                processing_message = "🔄 Создаю резюме текста, пожалуйста подождите..."
                try:
                    await query.edit_message_text(processing_message)
                except Exception as e:
                    logger.warning(f"Failed to update message to processing state: {e}")

                # Start progress tracker
                progress = ProgressTracker(
                    message=cast(Message, query.message),
                    duration_seconds=settings.llm_processing_duration,
                    rtf=1.0,  # For LLM, we use fixed duration, so RTF = 1.0
                    update_interval=settings.progress_update_interval,
                )
                await progress.start()

                # Generate summary
                try:
                    start_time = time.time()

                    # Run text processing with default length level
                    summary_text = await self.text_processor.summarize_text(
                        original_variant.text_content, length_level=target_length_level
                    )

                    processing_time = time.time() - start_time

                    # Stop progress tracker
                    await progress.stop()

                    # Save variant (UPSERT: handles race conditions)
                    # Check variant limit before creating
                    if await self._check_variant_limit(usage_id):
                        await query.answer("Достигнут лимит вариантов", show_alert=True)
                        return
                    variant, created = await self.variant_repo.get_or_create_variant(
                        usage_id=usage_id,
                        mode="summary",
                        text_content=summary_text,
                        length_level=target_length_level,
                        emoji_level=target_emoji_level,
                        timestamps_enabled=target_timestamps_enabled,
                        generated_by="llm",
                        llm_model=settings.llm_model,
                        processing_time_seconds=processing_time,
                    )
                    if created:
                        logger.info(
                            f"Generated summary text: usage_id={usage_id}, "
                            f"time={processing_time:.2f}s"
                        )
                    else:
                        logger.info(
                            f"Summary variant already exists: usage_id={usage_id}, "
                            "using cached version"
                        )

                except Exception as e:
                    # Stop progress tracker on error
                    await progress.stop()

                    logger.error(f"Failed to generate summary: {e}", exc_info=True)

                    # Restore original text and show error
                    try:
                        segments = await self.segment_repo.get_by_usage_id(usage_id)
                        has_segments = len(segments) > 0
                        await query.edit_message_text(
                            sanitize_html(original_variant.text_content),
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

                    # Try to answer query (may fail if query is too old)
                    try:
                        await query.answer("Не удалось создать резюме", show_alert=True)
                    except Exception as answer_error:
                        logger.warning(f"Failed to answer callback query: {answer_error}")
                    return

            elif new_mode == "magic":
                # Generate magic (publication-ready) text
                if not self.text_processor:
                    await query.answer(
                        "Обработка текста недоступна (LLM отключен)", show_alert=True
                    )
                    return

                # Get original text
                original_variant = await self.variant_repo.get_variant(
                    usage_id=usage_id, mode="original"
                )
                if not original_variant:
                    await query.answer("Исходный текст не найден", show_alert=True)
                    return

                # Acknowledge callback immediately
                await query.answer("Начинаю обработку...")

                # Edit message to show processing started
                processing_message = "🪄 Делаю красиво, пожалуйста подождите..."
                try:
                    await query.edit_message_text(processing_message)
                except Exception as e:
                    logger.warning(f"Failed to update message to processing state: {e}")

                # Start progress tracker
                progress = ProgressTracker(
                    message=cast(Message, query.message),
                    duration_seconds=settings.llm_processing_duration,
                    rtf=1.0,
                    update_interval=settings.progress_update_interval,
                )
                await progress.start()

                # Generate magic text
                try:
                    start_time = time.time()

                    magic_text = await self.text_processor.create_magic(
                        original_variant.text_content
                    )

                    processing_time = time.time() - start_time

                    # Stop progress tracker
                    await progress.stop()

                    # Save variant (UPSERT: handles race conditions)
                    # Check variant limit before creating
                    if await self._check_variant_limit(usage_id):
                        await query.answer("Достигнут лимит вариантов", show_alert=True)
                        return
                    variant, created = await self.variant_repo.get_or_create_variant(
                        usage_id=usage_id,
                        mode="magic",
                        text_content=magic_text,
                        length_level=target_length_level,
                        emoji_level=target_emoji_level,
                        timestamps_enabled=target_timestamps_enabled,
                        generated_by="llm",
                        llm_model=settings.llm_model,
                        processing_time_seconds=processing_time,
                    )
                    if created:
                        logger.info(
                            f"Generated magic text: usage_id={usage_id}, "
                            f"time={processing_time:.2f}s"
                        )
                    else:
                        logger.info(
                            f"Magic variant already exists: usage_id={usage_id}, "
                            "using cached version"
                        )

                except Exception as e:
                    logger.error(f"Failed to generate magic text: {e}", exc_info=True)
                    await progress.stop()

                    # Restore original text and show error
                    try:
                        segments = await self.segment_repo.get_by_usage_id(usage_id)
                        has_segments = len(segments) > 0
                        await query.edit_message_text(
                            sanitize_html(original_variant.text_content),
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

                    # Try to answer query (may fail if query is too old)
                    try:
                        await query.answer("Не удалось обработать текст", show_alert=True)
                    except Exception as answer_error:
                        logger.warning(f"Failed to answer callback query: {answer_error}")
                    return

            elif new_mode == "original":
                # Original variant should always exist, but handle gracefully
                variant = await self.variant_repo.get_variant(usage_id=usage_id, mode="original")
                if not variant:
                    await query.answer("Исходный текст не найден", show_alert=True)
                    return

        # Sanity check: variant should be set by now
        if not variant:
            logger.error("Variant is None after processing - should not happen")
            await query.answer("Внутренняя ошибка", show_alert=True)
            return

        # Update state with new mode and reset formatting parameters to defaults
        # Use the existing state_repo (no nested session)
        state.active_mode = new_mode
        state.emoji_level = target_emoji_level
        state.length_level = target_length_level
        state.timestamps_enabled = target_timestamps_enabled
        await self.state_repo.update(state)

        # Get segments info
        segments = await self.segment_repo.get_by_usage_id(usage_id)
        has_segments = len(segments) > 0

        # Update keyboard
        keyboard = create_transcription_keyboard(state, has_segments, settings)

        # Update message with new text (handles both text and file messages)
        try:
            await self.update_transcription_display(
                query, context, state, variant.text_content, keyboard, self.state_repo
            )
            logger.info(f"Mode changed successfully: usage_id={usage_id}, mode={new_mode}")
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
            await query.answer("Не удалось обновить сообщение", show_alert=True)

    async def handle_length_change(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle length adjustment (shorter/longer).

        Phase 3: Implements incremental length variations.

        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        data = decode_callback_data(query.data)
        usage_id = data["usage_id"]
        direction = data["direction"]  # "shorter" or "longer"

        logger.info(f"Length change request: usage_id={usage_id}, direction={direction}")

        # Validate feature is enabled
        if not settings.enable_length_variations:
            await query.answer("Изменение длины отключено", show_alert=True)
            return

        # Get current state
        state = await self.state_repo.get_by_usage_id(usage_id)
        if not state:
            await query.answer("Состояние не найдено", show_alert=True)
            return

        current_level = state.length_level

        # Check if transition is possible
        if current_level not in LEVEL_TRANSITIONS:
            await query.answer("Неизвестный уровень длины", show_alert=True)
            return

        if direction not in LEVEL_TRANSITIONS[current_level]:
            # At boundary - can't go further
            if direction == "shorter":
                await query.answer("Уже минимальная длина!", show_alert=True)
            else:
                await query.answer("Уже максимальная длина!", show_alert=True)
            return

        new_level = LEVEL_TRANSITIONS[current_level][direction]
        logger.info(f"Length transition: {current_level} -> {new_level} (direction={direction})")

        # Get or generate variant at new level
        variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=state.active_mode,
            length_level=new_level,
            emoji_level=state.emoji_level,
            timestamps_enabled=state.timestamps_enabled,
        )

        if not variant:
            # Need to generate variant
            if not self.text_processor:
                await query.answer("Обработка текста недоступна (LLM отключен)", show_alert=True)
                return

            # Get current level variant (base for adjustment)
            current_variant = await self.variant_repo.get_variant(
                usage_id=usage_id,
                mode=state.active_mode,
                length_level=current_level,
                emoji_level=state.emoji_level,
                timestamps_enabled=state.timestamps_enabled,
            )

            if not current_variant:
                await query.answer("Текущий вариант не найден", show_alert=True)
                return

            # Acknowledge callback immediately
            await query.answer("Генерирую вариант...")

            # Edit message to show processing
            processing_message = (
                f"🔄 {'Сокращаю' if direction == 'shorter' else 'Расширяю'} текст..."
            )
            try:
                await query.edit_message_text(processing_message)
            except Exception as e:
                logger.warning(f"Failed to update message to processing state: {e}")

            # Start progress tracker
            progress = ProgressTracker(
                message=cast(Message, query.message),
                duration_seconds=settings.llm_processing_duration,
                rtf=1.0,
                update_interval=settings.progress_update_interval,
            )
            await progress.start()

            # Generate adjusted text
            try:
                start_time = time.time()

                adjusted_text = await self.text_processor.adjust_length(
                    current_text=current_variant.text_content,
                    direction=direction,
                    current_level=current_level,
                    mode=state.active_mode,
                )

                processing_time = time.time() - start_time

                # Stop progress tracker
                await progress.stop()

                # Save variant
                variant = await self.variant_repo.create(
                    usage_id=usage_id,
                    mode=state.active_mode,
                    text_content=adjusted_text,
                    length_level=new_level,
                    emoji_level=state.emoji_level,
                    timestamps_enabled=state.timestamps_enabled,
                    generated_by="llm",
                    llm_model=settings.llm_model,
                    processing_time_seconds=processing_time,
                )
                logger.info(
                    f"Generated {direction} variant: usage_id={usage_id}, "
                    f"level={new_level}, time={processing_time:.2f}s"
                )

            except Exception as e:
                # Stop progress tracker on error
                await progress.stop()

                logger.error(f"Failed to adjust text length: {e}", exc_info=True)

                # Restore current text
                try:
                    segments = await self.segment_repo.get_by_usage_id(usage_id)
                    has_segments = len(segments) > 0
                    await query.edit_message_text(
                        sanitize_html(current_variant.text_content),
                        reply_markup=create_transcription_keyboard(state, has_segments, settings),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                await query.answer("Не удалось изменить длину текста", show_alert=True)
                return

        # Sanity check
        if not variant:
            logger.error("Variant is None after processing - should not happen")
            await query.answer("Внутренняя ошибка", show_alert=True)
            return

        # Update state
        state.length_level = new_level
        await self.state_repo.update(state)

        # Get segments info
        segments = await self.segment_repo.get_by_usage_id(usage_id)
        has_segments = len(segments) > 0

        # Update keyboard (will now show adjusted buttons)
        keyboard = create_transcription_keyboard(state, has_segments, settings)

        # Update message with new text (handles both text and file messages)
        try:
            await self.update_transcription_display(
                query, context, state, variant.text_content, keyboard, self.state_repo
            )
            logger.info(
                f"Length changed successfully: usage_id={usage_id}, "
                f"level={current_level}->{new_level}"
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
            await query.answer("Не удалось обновить сообщение", show_alert=True)

    async def handle_emoji_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle emoji level change (0/1/2).

        Phase 5: Implements emoji addition with three levels:
        - Level 0: No emojis
        - Level 1: Low (1-2 emojis)
        - Level 2: High (3-5 emojis)

        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        data = decode_callback_data(query.data)
        usage_id = data["usage_id"]
        direction = data.get("direction", "increase")  # "increase", "decrease", or "moderate"

        logger.info(f"Emoji toggle request: usage_id={usage_id}, direction={direction}")

        # Validate feature is enabled
        if not settings.enable_emoji_option:
            await query.answer("Опция смайлов отключена", show_alert=True)
            return

        # Get current state
        state = await self.state_repo.get_by_usage_id(usage_id)
        if not state:
            await query.answer("Состояние не найдено", show_alert=True)
            return

        current_emoji = state.emoji_level

        # Calculate new emoji level (4 levels: 0, 1, 2, 3)
        if direction == "few":
            # Direct jump to level 1 (few emojis) from level 0
            new_emoji = 1
        elif direction == "moderate":
            # Direct jump to level 2 (moderate) from level 0
            new_emoji = 2
        elif direction == "increase":
            new_emoji = min(current_emoji + 1, 3)
            if new_emoji == current_emoji:
                await query.answer("Больше смайлов нельзя!", show_alert=True)
                return
        else:  # decrease
            new_emoji = max(current_emoji - 1, 0)
            if new_emoji == current_emoji:
                await query.answer("Смайлы уже убраны!", show_alert=True)
                return

        logger.info(f"Emoji level change: {current_emoji} -> {new_emoji}")

        # Get or generate variant with new emoji level
        variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=state.active_mode,
            length_level=state.length_level,
            emoji_level=new_emoji,
            timestamps_enabled=state.timestamps_enabled,
        )

        if not variant:
            # Need to generate variant
            if not self.text_processor:
                await query.answer("Обработка текста недоступна (LLM отключен)", show_alert=True)
                return

            # Pick source text to transform
            # If adding emojis, prefer clean (level 0) text. If stripping, use current.
            source_variant = None
            if new_emoji > 0:
                source_variant = await self.variant_repo.get_variant(
                    usage_id=usage_id,
                    mode=state.active_mode,
                    length_level=state.length_level,
                    emoji_level=0,
                    timestamps_enabled=state.timestamps_enabled,
                )

            if not source_variant:
                source_variant = await self.variant_repo.get_variant(
                    usage_id=usage_id,
                    mode=state.active_mode,
                    length_level=state.length_level,
                    emoji_level=current_emoji,
                    timestamps_enabled=state.timestamps_enabled,
                )

            if not source_variant:
                source_variant = await self.variant_repo.get_variant(
                    usage_id=usage_id, mode="original"
                )

            if not source_variant:
                await query.answer("Исходный текст не найден", show_alert=True)
                return

            # Acknowledge callback immediately
            await query.answer("Обрабатываю смайлы...")

            # Edit message to show processing
            action_text = "Добавляю" if new_emoji > 0 else "Удаляю"
            processing_message = f"🔄 {action_text} смайлы в тексте..."
            try:
                await query.edit_message_text(processing_message)
            except Exception as e:
                logger.warning(f"Failed to update message to processing state: {e}")

            # Start progress tracker
            progress = ProgressTracker(
                message=cast(Message, query.message),
                duration_seconds=settings.llm_processing_duration,
                rtf=1.0,
                update_interval=settings.progress_update_interval,
            )
            await progress.start()

            # Generate text with emojis
            try:
                start_time = time.time()

                transformed_text = await self.text_processor.add_emojis(
                    source_variant.text_content, new_emoji, current_level=current_emoji
                )

                processing_time = time.time() - start_time

                # Stop progress tracker
                await progress.stop()

                # Save variant
                variant = await self.variant_repo.create(
                    usage_id=usage_id,
                    mode=state.active_mode,
                    text_content=transformed_text,
                    length_level=state.length_level,
                    emoji_level=new_emoji,
                    timestamps_enabled=state.timestamps_enabled,
                    generated_by="llm",
                    llm_model=settings.llm_model,
                    processing_time_seconds=processing_time,
                )
                logger.info(
                    f"Generated emoji variant: usage_id={usage_id}, "
                    f"level={new_emoji}, time={processing_time:.2f}s"
                )

            except Exception as e:
                # Stop progress tracker on error
                await progress.stop()

                logger.error(f"Failed to add emojis: {e}", exc_info=True)

                # Restore current text
                try:
                    current_variant = await self.variant_repo.get_variant(
                        usage_id=usage_id,
                        mode=state.active_mode,
                        length_level=state.length_level,
                        emoji_level=current_emoji,
                        timestamps_enabled=state.timestamps_enabled,
                    )
                    if current_variant:
                        segments = await self.segment_repo.get_by_usage_id(usage_id)
                        has_segments = len(segments) > 0
                        await query.edit_message_text(
                            sanitize_html(current_variant.text_content),
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
                            parse_mode="HTML",
                        )
                except Exception:
                    pass

                await query.answer("Не удалось добавить смайлы", show_alert=True)
                return

        # Sanity check
        if not variant:
            logger.error("Variant is None after processing - should not happen")
            await query.answer("Внутренняя ошибка", show_alert=True)
            return

        # Update state
        state.emoji_level = new_emoji
        await self.state_repo.update(state)

        # Get segments info
        segments = await self.segment_repo.get_by_usage_id(usage_id)
        has_segments = len(segments) > 0

        # Update keyboard (will now show emoji buttons)
        keyboard = create_transcription_keyboard(state, has_segments, settings)

        # Update message with new text (handles both text and file messages)
        try:
            await self.update_transcription_display(
                query, context, state, variant.text_content, keyboard, self.state_repo
            )
            logger.info(
                f"Emoji level changed successfully: usage_id={usage_id}, "
                f"level={current_emoji}->{new_emoji}"
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
            await query.answer("Не удалось обновить сообщение", show_alert=True)

    async def handle_timestamps_toggle(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle timestamps toggle (on/off).

        Phase 6: Implements timestamps formatting for segments (>5 min audio).
        Timestamps are applied to any mode (original/structured/summary).

        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        data = decode_callback_data(query.data)
        usage_id = data["usage_id"]

        logger.info(f"Timestamps toggle request: usage_id={usage_id}")

        # Validate feature is enabled
        if not settings.enable_timestamps_option:
            await query.answer("Опция таймкодов отключена", show_alert=True)
            return

        # Get current state
        state = await self.state_repo.get_by_usage_id(usage_id)
        if not state:
            await query.answer("Состояние не найдено", show_alert=True)
            return

        # Check if segments exist (required for timestamps)
        segments = await self.segment_repo.get_by_usage_id(usage_id)
        if not segments:
            await query.answer("Таймкоды недоступны для этого аудио", show_alert=True)
            return

        new_timestamps = not state.timestamps_enabled
        logger.info(f"Toggling timestamps: {state.timestamps_enabled} -> {new_timestamps}")

        # Get base variant (without timestamps)
        base_variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=state.active_mode,
            length_level=state.length_level,
            emoji_level=state.emoji_level,
            timestamps_enabled=False,
        )

        if not base_variant:
            await query.answer("Базовый текст не найден", show_alert=True)
            return

        if new_timestamps:
            # Enable timestamps: get or generate variant with timestamps
            variant = await self.variant_repo.get_variant(
                usage_id=usage_id,
                mode=state.active_mode,
                length_level=state.length_level,
                emoji_level=state.emoji_level,
                timestamps_enabled=True,
            )

            if not variant:
                # Generate variant with timestamps
                if not self.text_processor:
                    await query.answer("Обработка текста недоступна", show_alert=True)
                    return

                # Acknowledge callback immediately
                await query.answer("Добавляю таймкоды...")

                # Format text with timestamps (synchronous operation)
                text_with_timestamps = self.text_processor.format_with_timestamps(
                    segments, base_variant.text_content, state.active_mode
                )

                # Save variant
                variant = await self.variant_repo.create(
                    usage_id=usage_id,
                    mode=state.active_mode,
                    text_content=text_with_timestamps,
                    length_level=state.length_level,
                    emoji_level=state.emoji_level,
                    timestamps_enabled=True,
                    generated_by="formatting",
                )
                logger.info(f"Generated timestamps variant: usage_id={usage_id}")

            text = variant.text_content
        else:
            # Disable timestamps: use base variant
            text = base_variant.text_content

        # Update state
        state.timestamps_enabled = new_timestamps
        await self.state_repo.update(state)

        # Get segments info (always true here since we checked above)
        has_segments = len(segments) > 0

        # Update keyboard (button label will change)
        keyboard = create_transcription_keyboard(state, has_segments, settings)

        # Update message with new text (handles both text and file messages)
        try:
            await self.update_transcription_display(
                query, context, state, text, keyboard, self.state_repo
            )
            logger.info(
                f"Timestamps toggled successfully: usage_id={usage_id}, "
                f"enabled={new_timestamps}"
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
            await query.answer("Не удалось обновить сообщение", show_alert=True)

    async def handle_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle back button to return to main keyboard from submenus.

        This handler restores the main transcription keyboard without changing
        the active mode or any parameters. Used when returning from retranscribe menu.

        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        data = decode_callback_data(query.data)
        usage_id = data["usage_id"]

        logger.info(f"Back button pressed: usage_id={usage_id}")

        # Get current state
        state = await self.state_repo.get_by_usage_id(usage_id)
        if not state:
            await query.answer("Состояние не найдено", show_alert=True)
            return

        # Get segments info
        segments = await self.segment_repo.get_by_usage_id(usage_id)
        has_segments = len(segments) > 0

        # Get current variant to display
        variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=state.active_mode,
            length_level=state.length_level,
            emoji_level=state.emoji_level,
            timestamps_enabled=state.timestamps_enabled,
        )

        if not variant:
            await query.answer("Текст не найден", show_alert=True)
            return

        # Create main keyboard
        keyboard = create_transcription_keyboard(state, has_segments, settings)

        # Update message with current text and main keyboard
        try:
            await self.update_transcription_display(
                query, context, state, variant.text_content, keyboard, self.state_repo
            )
            logger.info(f"Returned to main keyboard: usage_id={usage_id}")
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
            await query.answer("Не удалось обновить сообщение", show_alert=True)
