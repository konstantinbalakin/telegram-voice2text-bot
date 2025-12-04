"""Callback query handlers for interactive transcription."""

import logging
import time
from typing import Optional, cast
from telegram import Update, Message
from telegram.ext import ContextTypes

from src.bot.keyboards import decode_callback_data, create_transcription_keyboard
from src.storage.repositories import (
    TranscriptionStateRepository,
    TranscriptionVariantRepository,
    TranscriptionSegmentRepository,
)
from src.services.text_processor import TextProcessor
from src.services.progress_tracker import ProgressTracker
from src.config import settings

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
        text_processor: Optional[TextProcessor] = None,
    ):
        """
        Initialize callback handlers.

        Args:
            state_repo: Repository for transcription states
            variant_repo: Repository for transcription variants
            segment_repo: Repository for transcription segments
            text_processor: Text processor for LLM operations (optional)
        """
        self.state_repo = state_repo
        self.variant_repo = variant_repo
        self.segment_repo = segment_repo
        self.text_processor = text_processor

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
            # Note: Additional handlers will be added in future phases:
            # - retranscribe_menu, retranscribe: Phase 8
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

        if new_mode not in ["original", "structured", "summary"]:
            await query.answer("Функция будет доступна в следующих версиях", show_alert=True)
            return

        # Get or generate variant
        variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=new_mode,
            length_level=state.length_level,
            emoji_level=state.emoji_level,
            timestamps_enabled=state.timestamps_enabled,
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

                    # Save variant (check if already exists first to avoid UNIQUE constraint error)
                    existing_variant = await self.variant_repo.get_variant(
                        usage_id=usage_id,
                        mode="structured",
                        length_level="default",
                        emoji_level=0,
                        timestamps_enabled=False,
                    )

                    if existing_variant:
                        # Variant already exists (race condition or retry), use it
                        logger.info(
                            f"Structured variant already exists: usage_id={usage_id}, "
                            "using cached version"
                        )
                        variant = existing_variant
                    else:
                        # Create new variant
                        variant = await self.variant_repo.create(
                            usage_id=usage_id,
                            mode="structured",
                            text_content=structured_text,
                            length_level="default",
                            emoji_level=0,
                            timestamps_enabled=False,
                            generated_by="llm",
                            llm_model=settings.llm_model,
                            processing_time_seconds=processing_time,
                        )
                        logger.info(
                            f"Generated structured text: usage_id={usage_id}, "
                            f"time={processing_time:.2f}s"
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
                            original_variant.text_content,
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
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

                    # Run text processing
                    summary_text = await self.text_processor.summarize_text(
                        original_variant.text_content, length_level=state.length_level
                    )

                    processing_time = time.time() - start_time

                    # Stop progress tracker
                    await progress.stop()

                    # Save variant (check if already exists first to avoid UNIQUE constraint error)
                    existing_variant = await self.variant_repo.get_variant(
                        usage_id=usage_id,
                        mode="summary",
                        length_level=state.length_level,
                        emoji_level=state.emoji_level,
                        timestamps_enabled=state.timestamps_enabled,
                    )

                    if existing_variant:
                        # Variant already exists (race condition or retry), use it
                        logger.info(
                            f"Summary variant already exists: usage_id={usage_id}, "
                            "using cached version"
                        )
                        variant = existing_variant
                    else:
                        # Create new variant
                        variant = await self.variant_repo.create(
                            usage_id=usage_id,
                            mode="summary",
                            text_content=summary_text,
                            length_level=state.length_level,
                            emoji_level=state.emoji_level,
                            timestamps_enabled=state.timestamps_enabled,
                            generated_by="llm",
                            llm_model=settings.llm_model,
                            processing_time_seconds=processing_time,
                        )
                        logger.info(
                            f"Generated summary text: usage_id={usage_id}, "
                            f"time={processing_time:.2f}s"
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
                            original_variant.text_content,
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
                        )
                    except Exception:
                        pass

                    # Try to answer query (may fail if query is too old)
                    try:
                        await query.answer("Не удалось создать резюме", show_alert=True)
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

        # Update state
        state.active_mode = new_mode
        await self.state_repo.update(state)

        # Get segments info
        segments = await self.segment_repo.get_by_usage_id(usage_id)
        has_segments = len(segments) > 0

        # Update keyboard
        keyboard = create_transcription_keyboard(state, has_segments, settings)

        # Update message with new text
        try:
            await query.edit_message_text(variant.text_content, reply_markup=keyboard)
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
                        current_variant.text_content,
                        reply_markup=create_transcription_keyboard(state, has_segments, settings),
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

        # Update message with new text
        try:
            await query.edit_message_text(variant.text_content, reply_markup=keyboard)
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
        if direction == "moderate":
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

        # Get base variant (without emojis)
        base_variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=state.active_mode,
            length_level=state.length_level,
            emoji_level=0,
            timestamps_enabled=state.timestamps_enabled,
        )

        if not base_variant:
            await query.answer("Базовый текст не найден", show_alert=True)
            return

        # Get or generate variant with new emoji level
        variant = await self.variant_repo.get_variant(
            usage_id=usage_id,
            mode=state.active_mode,
            length_level=state.length_level,
            emoji_level=new_emoji,
            timestamps_enabled=state.timestamps_enabled,
        )

        if not variant:
            # Need to generate variant with emojis
            if not self.text_processor:
                await query.answer("Обработка текста недоступна (LLM отключен)", show_alert=True)
                return

            # Acknowledge callback immediately
            await query.answer("Добавляю смайлы...")

            # Edit message to show processing
            processing_message = "🔄 Добавляю смайлы в текст..."
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

                text_with_emojis = await self.text_processor.add_emojis(
                    base_variant.text_content, new_emoji
                )

                processing_time = time.time() - start_time

                # Stop progress tracker
                await progress.stop()

                # Save variant
                variant = await self.variant_repo.create(
                    usage_id=usage_id,
                    mode=state.active_mode,
                    text_content=text_with_emojis,
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
                            current_variant.text_content,
                            reply_markup=create_transcription_keyboard(
                                state, has_segments, settings
                            ),
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

        # Update message with new text
        try:
            await query.edit_message_text(variant.text_content, reply_markup=keyboard)
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

        # Update message with new text
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
            logger.info(
                f"Timestamps toggled successfully: usage_id={usage_id}, "
                f"enabled={new_timestamps}"
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")
            await query.answer("Не удалось обновить сообщение", show_alert=True)
