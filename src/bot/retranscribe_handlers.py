"""Retranscription handlers for Phase 8."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.bot.keyboards import (
    decode_callback_data,
    encode_callback_data,
    create_transcription_keyboard,
)
from src.storage.repositories import (
    UsageRepository,
    TranscriptionStateRepository,
    TranscriptionVariantRepository,
    TranscriptionSegmentRepository,
)
from src.storage.database import get_session
from src.config import settings
from src.transcription.models import TranscriptionContext

if TYPE_CHECKING:
    from src.bot.handlers import BotHandlers

logger = logging.getLogger(__name__)


async def handle_retranscribe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show retranscribe options menu (Phase 8).

    Args:
        update: Telegram update
        context: Bot context
    """
    query = update.callback_query
    if not query or not query.data:
        return

    data = decode_callback_data(query.data)
    usage_id = data["usage_id"]

    logger.info(f"Retranscribe menu request: usage_id={usage_id}")

    # Validate feature is enabled
    if not settings.enable_retranscribe:
        await query.answer("Ретранскрипция отключена", show_alert=True)
        return

    # Get usage record to check if audio file exists
    async with get_session() as session:
        usage_repo = UsageRepository(session)
        usage = await usage_repo.get_by_id(usage_id)

        if not usage or not usage.original_file_path:
            await query.answer("Аудио файл недоступен для ретранскрипции", show_alert=True)
            return

    # Calculate wait time for free option (RTF 0.5 for medium model)
    duration_seconds = usage.voice_duration_seconds if usage.voice_duration_seconds else 0
    wait_time_seconds = int(
        duration_seconds * settings.retranscribe_free_model_rtf
    )  # RTF 0.5 for medium model

    # Format wait time
    if wait_time_seconds < 60:
        wait_time_str = f"{wait_time_seconds}с"
    else:
        minutes = wait_time_seconds // 60
        seconds = wait_time_seconds % 60
        wait_time_str = f"{minutes}м {seconds}с" if seconds > 0 else f"{minutes}м"

    # Calculate cost for paid option
    duration_minutes = duration_seconds / 60
    estimated_cost = duration_minutes * settings.retranscribe_paid_cost_per_minute

    keyboard = [
        [
            InlineKeyboardButton(
                f"🆓 Бесплатно (но дольше, ~{wait_time_str})",
                callback_data=encode_callback_data("retranscribe", usage_id, method="free"),
            )
        ],
        [
            InlineKeyboardButton(
                f"💰 Платно (~{estimated_cost:.1f}₽) - OpenAI",
                callback_data=encode_callback_data("retranscribe", usage_id, method="paid"),
            )
        ],
        [
            InlineKeyboardButton(
                "◀️ Назад",
                callback_data=encode_callback_data("mode", usage_id, mode="original"),
            )
        ],
    ]

    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer("Выберите метод ретранскрипции")
    except Exception as e:
        logger.error(f"Failed to show retranscribe menu: {e}")
        await query.answer("Не удалось показать меню", show_alert=True)


async def handle_retranscribe(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    bot_handlers: "BotHandlers",
) -> None:
    """Handle retranscription request (Phase 8).

    Args:
        update: Telegram update
        context: Bot context
        bot_handlers: BotHandlers instance for accessing transcription_router
    """
    query = update.callback_query
    if not query or not query.data or not query.message:
        return

    data = decode_callback_data(query.data)
    usage_id = data["usage_id"]
    method = data.get("method", "free")  # "free" or "paid"

    logger.info(f"Retranscribe request: usage_id={usage_id}, method={method}")

    # Validate feature is enabled
    if not settings.enable_retranscribe:
        await query.answer("Ретранскрипция отключена", show_alert=True)
        return

    # Get usage record and check file exists
    async with get_session() as session:
        usage_repo = UsageRepository(session)
        usage = await usage_repo.get_by_id(usage_id)

        if not usage or not usage.original_file_path:
            await query.answer("Аудио файл недоступен", show_alert=True)
            return

        # Check file exists on disk
        audio_path = Path(usage.original_file_path)
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            await query.answer("Аудио файл не найден", show_alert=True)
            return

    # Acknowledge and show processing message
    await query.answer("Начинаю ретранскрипцию...")

    processing_message = (
        "🔄 Запускаю ретранскрипцию с улучшенными параметрами...\n\n"
        f"Метод: {'Бесплатный (лучшая модель)' if method == 'free' else 'Платный (OpenAI)'}"
    )

    try:
        await query.edit_message_text(processing_message)
    except Exception as e:
        logger.warning(f"Failed to update message: {e}")

    # Delete old variants and reset state
    async with get_session() as session:
        variant_repo = TranscriptionVariantRepository(session)
        state_repo = TranscriptionStateRepository(session)
        segment_repo = TranscriptionSegmentRepository(session)

        # Delete old variants
        await variant_repo.delete_by_usage_id(usage_id)

        # Delete old segments
        await segment_repo.delete_by_usage_id(usage_id)

        # Reset state to defaults
        state = await state_repo.get_by_usage_id(usage_id)
        if state:
            state.active_mode = "original"
            state.length_level = "default"
            state.emoji_level = 0
            state.timestamps_enabled = False
            await state_repo.update(state)

        await session.commit()
        logger.info(f"Reset transcription state for usage_id={usage_id}")

    # Configure transcription context based on method
    if method == "free":
        # Free: Use better model (medium) - configured in settings
        # Format: faster-whisper-{model_name}
        provider_name = f"faster-whisper-{settings.retranscribe_free_model}"
        transcription_context = TranscriptionContext(
            language="ru",
            provider_preference=provider_name,  # e.g., "faster-whisper-medium"
        )
    else:
        # Paid: Use OpenAI
        transcription_context = TranscriptionContext(
            language="ru",
            provider_preference=settings.retranscribe_paid_provider,  # "openai"
        )

    logger.info(
        f"Retranscribing with context: provider={transcription_context.provider_preference}"
    )

    # Perform retranscription
    try:
        # Call TranscriptionRouter to retranscribe
        result = await bot_handlers.transcription_router.transcribe(
            audio_path,
            transcription_context,
        )

        logger.info(
            f"Retranscription completed: usage_id={usage_id}, "
            f"provider={result.provider_used}, text_length={len(result.text)}"
        )

        # Update usage record with new transcription stats
        async with get_session() as session:
            usage_repo = UsageRepository(session)
            await usage_repo.update(
                usage_id=usage_id,
                model_size=result.model_name or result.provider_used,
                processing_time_seconds=result.processing_time,
                transcription_length=len(result.text),
            )
            await session.commit()

        # Get current state and create callback handlers
        # Import here to avoid circular import
        from src.bot.callbacks import CallbackHandlers

        async with get_session() as session:
            state_repo = TranscriptionStateRepository(session)
            variant_repo = TranscriptionVariantRepository(session)
            segment_repo = TranscriptionSegmentRepository(session)

            state = await state_repo.get_by_usage_id(usage_id)

            if not state:
                logger.error(f"State not found for usage_id={usage_id}")
                await query.answer("Состояние не найдено", show_alert=True)
                return

            # Get segments info
            segments = await segment_repo.get_by_usage_id(usage_id)
            has_segments = len(segments) > 0

            # Create keyboard
            keyboard = create_transcription_keyboard(state, has_segments, settings)

            # Create CallbackHandlers instance for update_transcription_display
            callback_handlers = CallbackHandlers(
                state_repo, variant_repo, segment_repo, None, bot_handlers
            )

            # Update message with new transcription (handles both text and file messages)
            try:
                await callback_handlers.update_transcription_display(
                    query, context, state, result.text, keyboard
                )
                logger.info(f"Retranscription message updated for usage_id={usage_id}")
            except Exception as e:
                logger.error(f"Failed to update message with retranscription: {e}")
                try:
                    await query.answer(
                        "Ретранскрипция завершена, но не удалось обновить сообщение",
                        show_alert=True,
                    )
                except Exception:
                    pass  # Query too old, ignore

    except Exception as e:
        logger.error(f"Retranscription failed: {e}", exc_info=True)
        try:
            await query.edit_message_text(
                "❌ Произошла ошибка при ретранскрипции. Пожалуйста, попробуйте еще раз."
            )
        except Exception:
            pass  # Query too old, ignore

        try:
            await query.answer("Ошибка ретранскрипции", show_alert=True)
        except Exception:
            pass  # Query too old, ignore
