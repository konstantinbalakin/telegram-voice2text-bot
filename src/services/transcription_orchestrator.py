"""Transcription orchestration service.

Handles the full transcription pipeline: preprocessing, transcription,
LLM processing (structuring/refinement), and result delivery.
"""

import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from telegram import InlineKeyboardMarkup, Message

from src.config import settings
from src.storage.database import get_session
from src.storage.repositories import (
    UsageRepository,
    TranscriptionStateRepository,
    TranscriptionSegmentRepository,
    TranscriptionVariantRepository,
)
from src.transcription.routing.router import TranscriptionRouter
from src.transcription.routing.strategies import HybridStrategy
from src.transcription.audio_handler import AudioHandler
from src.transcription.models import TranscriptionResult
from src.services.queue_manager import TranscriptionRequest
from src.services.progress_tracker import ProgressTracker
from src.services.pdf_generator import create_file_object
from src.services.llm_service import LLMService
from src.services.text_processor import TextProcessor
from src.bot.keyboards import create_transcription_keyboard
from src.utils.markdown_utils import sanitize_markdown, escape_markdownv2

logger = logging.getLogger(__name__)

# Telegram message length limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# Debug text preview truncation length
DEBUG_TEXT_PREVIEW_LENGTH = 1500


def save_audio_file_for_retranscription(
    temp_file_path: Path, usage_id: int, file_identifier: str
) -> Optional[Path]:
    """Save audio file to persistent storage for retranscription.

    Args:
        temp_file_path: Temporary file path (original or preprocessed)
        usage_id: Usage record ID
        file_identifier: File identifier (telegram file_id or unique suffix)

    Returns:
        Path to saved file or None if saving failed or retranscription is disabled
    """
    if not settings.enable_retranscribe:
        logger.debug("Retranscription disabled, skipping file save")
        return None

    try:
        persistent_dir = Path(settings.persistent_audio_dir)
        persistent_dir.mkdir(parents=True, exist_ok=True)

        file_extension = temp_file_path.suffix or ".ogg"
        permanent_path = persistent_dir / f"{uuid.uuid4().hex}{file_extension}"

        shutil.copy2(temp_file_path, permanent_path)
        logger.info(f"Audio file saved for retranscription: {permanent_path}")

        return permanent_path

    except Exception as e:
        logger.error(f"Failed to save audio file for retranscription: {e}", exc_info=True)
        return None


class TranscriptionOrchestrator:
    """Orchestrates the full transcription pipeline."""

    def __init__(
        self,
        transcription_router: TranscriptionRouter,
        audio_handler: AudioHandler,
        llm_service: Optional[LLMService] = None,
        text_processor: Optional[TextProcessor] = None,
    ):
        self.transcription_router = transcription_router
        self.audio_handler = audio_handler
        self.llm_service = llm_service
        self.text_processor = text_processor

    async def _create_interactive_state_and_keyboard(
        self,
        usage_id: int,
        message_id: int,
        chat_id: int,
        result: TranscriptionResult,
        final_text: str,
        is_file_message: bool = False,
        file_message_id: Optional[int] = None,
        active_mode: str = "original",
        emoji_level: int = 0,
    ) -> Optional[InlineKeyboardMarkup]:
        """Create TranscriptionState, save segments, save original variant, and generate keyboard.

        Args:
            usage_id: Usage record ID
            message_id: Telegram message ID where transcription was sent
            chat_id: Telegram chat ID
            result: TranscriptionResult with optional segments
            final_text: The final text that was sent to the user
            is_file_message: Whether transcription was sent as file
            file_message_id: Message ID of the file message
            active_mode: Initial active mode
            emoji_level: Initial emoji level

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

                state = await state_repo.get_by_usage_id(usage_id)
                if not state:
                    # Clean up stale placeholder state (message_id=0) for this chat
                    # to avoid UNIQUE constraint violation on (message_id, chat_id)
                    if message_id == 0:
                        stale_state = await state_repo.get_by_message(0, chat_id)
                        if stale_state:
                            logger.warning(
                                f"Removing stale state with message_id=0: "
                                f"id={stale_state.id}, usage_id={stale_state.usage_id}"
                            )
                            await session.delete(stale_state)
                            await session.flush()

                    state = await state_repo.create(
                        usage_id=usage_id,
                        message_id=message_id,
                        chat_id=chat_id,
                        is_file_message=is_file_message,
                        file_message_id=file_message_id,
                    )
                    state.active_mode = active_mode
                    state.emoji_level = emoji_level
                    await session.flush()
                    logger.debug(
                        f"TranscriptionState created: id={state.id}, usage_id={usage_id}, "
                        f"message_id={message_id}, is_file={is_file_message}, "
                        f"file_msg_id={file_message_id}, "
                        f"active_mode={active_mode}, emoji_level={emoji_level}"
                    )
                else:
                    logger.debug(
                        f"Using existing TranscriptionState: id={state.id}, usage_id={usage_id}"
                    )

                existing_variant = await variant_repo.get_variant(
                    usage_id=usage_id,
                    mode="original",
                    length_level="default",
                    emoji_level=0,
                    timestamps_enabled=False,
                )
                if not existing_variant:
                    await variant_repo.create(
                        usage_id=usage_id,
                        mode="original",
                        text_content=final_text,
                        generated_by="transcription",
                    )
                    logger.debug(f"Created original variant for usage_id={usage_id}")
                else:
                    logger.debug(f"Original variant already exists for usage_id={usage_id}")

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
        prefix: str = "",
    ) -> tuple[Message, Optional[Message]]:
        """Send transcription result as text message or file based on length.

        Args:
            request: Transcription request
            text: Text content to send
            keyboard: Inline keyboard markup (optional)
            usage_id: Usage record ID
            prefix: Optional prefix for short messages

        Returns:
            (main_message, file_message)
        """
        async with get_session() as session:
            usage_repo = UsageRepository(session)
            usage = await usage_repo.get_by_id(usage_id)
            if usage:
                file_number = await usage_repo.count_by_user_id(usage.user_id)
            else:
                file_number = usage_id
                logger.warning(f"Usage {usage_id} not found, using usage_id as file_number")

        cleaned_text = sanitize_markdown(text)
        escaped_text = escape_markdownv2(cleaned_text)

        if len(cleaned_text) <= settings.file_threshold_chars:
            msg = await request.user_message.reply_text(
                prefix + escaped_text, reply_markup=keyboard, parse_mode="MarkdownV2"
            )
            logger.debug(
                f"Sent text result: usage_id={usage_id}, length={len(cleaned_text)}, "
                f"threshold={settings.file_threshold_chars}"
            )
            return (msg, None)
        else:
            info_msg = await request.user_message.reply_text(
                "📝 Транскрипция готова! Файл ниже ↓", reply_markup=keyboard
            )

            file_obj, file_extension = create_file_object(cleaned_text, f"{file_number}_original")

            file_msg = await request.user_message.reply_document(
                document=file_obj,
                filename=file_obj.name,
                caption=escape_markdownv2(
                    f"📄 Транскрипция ({len(cleaned_text)} символов, {file_extension})"
                ),
                parse_mode="MarkdownV2",
            )

            logger.debug(
                f"Sent file result: usage_id={usage_id}, length={len(cleaned_text)}, "
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
        async with get_session() as session:
            usage_repo = UsageRepository(session)
            usage = await usage_repo.get_by_id(request.usage_id)
            if usage:
                file_number = await usage_repo.count_by_user_id(usage.user_id)
            else:
                file_number = request.usage_id
                logger.warning(f"Usage {request.usage_id} not found, using usage_id as file_number")

        try:
            await request.status_message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete status message: {e}")

        escaped_draft = escape_markdownv2(draft_text)

        if len(draft_text) <= settings.file_threshold_chars:
            logger.debug(
                f"Sending short draft as text: request_id={request.id}, length={len(draft_text)}"
            )
            message = await request.user_message.reply_text(
                f"✅ Черновик готов:\n\n{escaped_draft}\n\n🔄 Улучшаю текст\\.\\.\\.",
                parse_mode="MarkdownV2",
            )
            request.draft_messages.append(message)
        else:
            logger.debug(
                f"Sending long draft as file: request_id={request.id}, length={len(draft_text)}"
            )

            info_msg = await request.user_message.reply_text(
                "✅ Черновик готов! Файл ниже ↓\n\n🔄 Улучшаю текст..."
            )
            request.draft_messages.append(info_msg)

            file_obj, file_extension = create_file_object(draft_text, f"{file_number}_draft")

            file_msg = await request.user_message.reply_document(
                document=file_obj,
                filename=file_obj.name,
                caption=escape_markdownv2(
                    f"📄 Черновик ({len(draft_text)} символов, {file_extension})"
                ),
                parse_mode="MarkdownV2",
            )
            request.draft_messages.append(file_msg)

    async def _preprocess_audio(self, request: TranscriptionRequest) -> tuple[Path, Path | None]:
        """Preprocess audio and optionally save for retranscription.

        Args:
            request: Transcription request from queue

        Returns:
            Tuple of (processed_path, persistent_path)
        """
        processed_path = request.file_path
        try:
            should_preprocess = (
                settings.audio_convert_to_mono or settings.audio_speed_multiplier != 1.0
            )

            if should_preprocess:
                await request.status_message.edit_text("🔧 Оптимизирую аудио...")
                logger.info("Starting audio preprocessing...")

            target_provider = None
            target_model = None
            if self.transcription_router:
                target_provider = self.transcription_router.get_active_provider_name()
                target_model = self.transcription_router.get_active_provider_model()
                logger.debug(
                    f"Target provider for preprocessing: {target_provider}, "
                    f"model: {target_model}"
                )

            processed_path = await self.audio_handler.preprocess_audio(
                request.file_path,
                target_provider=target_provider,
                target_model=target_model,
            )

            if processed_path != request.file_path:
                logger.info(f"Audio preprocessed: {processed_path.name}")
        except Exception as e:
            logger.warning(f"Audio preprocessing failed: {e}, using original")
            processed_path = request.file_path

        persistent_path = None
        if settings.enable_retranscribe:
            try:
                original_file_id = request.file_path.stem.split("_")[0]
                file_to_save = (
                    processed_path if processed_path != request.file_path else request.file_path
                )
                persistent_path = save_audio_file_for_retranscription(
                    file_to_save, request.usage_id, original_file_id
                )

                if persistent_path:
                    async with get_session() as session:
                        usage_repo = UsageRepository(session)
                        await usage_repo.update(
                            usage_id=request.usage_id,
                            original_file_path=str(persistent_path),
                        )
                    logger.info(
                        f"Saved {'preprocessed' if processed_path != request.file_path else 'original'} "
                        f"audio for retranscription: {persistent_path}"
                    )
            except Exception as e:
                logger.error(f"Failed to save audio for retranscription: {e}", exc_info=True)

        return processed_path, persistent_path

    async def _run_transcription(
        self,
        request: TranscriptionRequest,
        processed_path: Path,
        progress: ProgressTracker,
    ) -> TranscriptionResult:
        """Run transcription and stop progress tracker.

        Args:
            request: Transcription request from queue
            processed_path: Path to preprocessed audio file
            progress: Active progress tracker to stop after transcription

        Returns:
            TranscriptionResult
        """
        await request.status_message.edit_text("⚙️ Обрабатываю запись...")

        result = await self.transcription_router.transcribe(
            processed_path,
            request.context,
        )

        await progress.stop()
        return result

    async def _apply_structuring(
        self,
        request: TranscriptionRequest,
        result: TranscriptionResult,
        show_draft: bool,
        emoji_level: int,
    ) -> tuple[str, float]:
        """Apply structuring via LLM (StructureStrategy flow).

        Args:
            request: Transcription request
            result: Transcription result
            show_draft: Whether to show draft messages
            emoji_level: Emoji level for structuring

        Returns:
            Tuple of (structured_text, llm_processing_time)
        """
        async with get_session() as session:
            variant_repo = TranscriptionVariantRepository(session)
            await variant_repo.create(
                usage_id=request.usage_id,
                mode="original",
                text_content=result.text,
                length_level="default",
                emoji_level=0,
                timestamps_enabled=False,
                generated_by="whisper",
                llm_model=None,
                processing_time_seconds=result.processing_time,
            )
            logger.info(f"Saved original variant: usage_id={request.usage_id}")

        if show_draft:
            await self._send_draft_messages(request, result.text)
            logger.info("Draft messages sent, starting structuring...")

        structure_start = time.time()

        assert self.text_processor is not None
        structured_text = await self.text_processor.create_structured(
            original_text=result.text,
            length_level="default",
            emoji_level=emoji_level,
        )

        structure_time = time.time() - structure_start
        logger.info(f"Structuring completed in {structure_time:.2f}s")

        async with get_session() as session:
            variant_repo = TranscriptionVariantRepository(session)
            await variant_repo.create(
                usage_id=request.usage_id,
                mode="structured",
                text_content=structured_text,
                length_level="default",
                emoji_level=emoji_level,
                timestamps_enabled=False,
                generated_by="llm",
                llm_model=settings.llm_model,
                processing_time_seconds=structure_time,
            )
            logger.info(f"Saved structured variant: usage_id={request.usage_id}")

        async with get_session() as session:
            usage_repo = UsageRepository(session)
            await usage_repo.update(
                usage_id=request.usage_id,
                llm_processing_time_seconds=structure_time,
            )
            logger.debug(f"LLM processing time saved to database: {structure_time:.2f}s")

        if show_draft:
            for msg in request.draft_messages:
                try:
                    await msg.delete()
                    logger.debug(f"Deleted draft message: request_id={request.id}")
                except Exception as e:
                    logger.warning(f"Failed to delete draft message: {e}")
        else:
            try:
                await request.status_message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete status message: {e}")

        return structured_text, structure_time

    async def _apply_refinement(
        self,
        request: TranscriptionRequest,
        result: TranscriptionResult,
    ) -> tuple[str, float]:
        """Apply LLM refinement (HybridStrategy flow).

        Args:
            request: Transcription request
            result: Transcription result

        Returns:
            Tuple of (refined_text, llm_processing_time)
        """
        draft_text = result.text
        await self._send_draft_messages(request, draft_text)

        assert self.llm_service is not None
        llm_start = time.time()
        refined_text = await self.llm_service.refine_transcription(draft_text)
        llm_time = time.time() - llm_start
        logger.info(f"LLM refinement took {llm_time:.2f}s")

        async with get_session() as session:
            usage_repo = UsageRepository(session)
            await usage_repo.update(
                usage_id=request.usage_id,
                llm_processing_time_seconds=llm_time,
            )
            logger.debug(f"LLM processing time saved to database: {llm_time:.2f}s")

        for msg in request.draft_messages:
            try:
                await msg.delete()
                logger.debug(f"Deleted draft message: request_id={request.id}")
            except Exception as e:
                logger.warning(f"Failed to delete draft message: {e}")

        if not request.draft_messages:
            try:
                await request.status_message.delete()
                logger.debug(f"Deleted status message (short draft): request_id={request.id}")
            except Exception as e:
                logger.warning(f"Failed to delete status message: {e}")

        if settings.llm_debug_mode:
            try:
                escaped_draft = escape_markdownv2(draft_text)
                escaped_refined = escape_markdownv2(refined_text)
                debug_message = (
                    "🔍 *Сравнение \\(LLM\\_DEBUG\\_MODE\\=true\\)*\n\n"
                    f"📝 *Черновик \\({escape_markdownv2(result.model_name)}\\):*\n"
                    f"`{escaped_draft}`\n\n"
                    f"✨ *После LLM \\({escape_markdownv2(settings.llm_model)}\\):*\n"
                    f"`{escaped_refined}`"
                )
                if len(debug_message) > 4000:
                    debug_message = (
                        "🔍 *Сравнение \\(LLM\\_DEBUG\\_MODE\\=true\\)*\n\n"
                        f"📝 *Черновик:* {len(draft_text)} символов\n"
                        f"`{escaped_draft[:DEBUG_TEXT_PREVIEW_LENGTH]}\\.\\.\\.`\n\n"
                        f"✨ *После LLM:* {len(refined_text)} символов\n"
                        f"`{escaped_refined[:DEBUG_TEXT_PREVIEW_LENGTH]}\\.\\.\\.`\n\n"
                        f"ℹ️ Тексты слишком длинные, показаны первые {DEBUG_TEXT_PREVIEW_LENGTH} символов"
                    )
                await request.user_message.reply_text(debug_message, parse_mode="MarkdownV2")
            except Exception as e:
                logger.warning(f"Failed to send LLM debug comparison: {e}")

        return refined_text, llm_time

    async def _send_result_and_update_state(
        self,
        request: TranscriptionRequest,
        text: str,
        result: TranscriptionResult,
        active_mode: str = "original",
        emoji_level: int = 0,
    ) -> None:
        """Send transcription result to user and update interactive state.

        Args:
            request: Transcription request
            text: Final text to send
            result: Transcription result (for segments)
            active_mode: Active mode for interactive state
            emoji_level: Emoji level for interactive state
        """
        keyboard = await self._create_interactive_state_and_keyboard(
            usage_id=request.usage_id,
            message_id=0,
            chat_id=request.user_message.chat_id,
            result=result,
            final_text=text,
            active_mode=active_mode,
            emoji_level=emoji_level,
        )

        main_msg, file_msg = await self._send_transcription_result(
            request=request,
            text=text,
            keyboard=keyboard,
            usage_id=request.usage_id,
            prefix="",
        )

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

    async def process_transcription(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Process transcription request (called by queue worker).

        Args:
            request: Transcription request from queue

        Returns:
            TranscriptionResult on success

        Raises:
            Exception on error
        """
        logger.info(f"Processing transcription request {request.id}")

        progress = ProgressTracker(
            message=request.status_message,
            duration_seconds=request.duration_seconds,
            rtf=settings.progress_rtf,
            update_interval=settings.progress_update_interval,
        )
        await progress.start()

        processed_path = request.file_path

        try:
            processed_path, persistent_path = await self._preprocess_audio(request)

            result = await self._run_transcription(request, processed_path, progress)

            needs_refinement = False
            if isinstance(self.transcription_router.strategy, HybridStrategy):
                needs_refinement = self.transcription_router.strategy.requires_refinement(
                    request.duration_seconds
                )

            if request.context.disable_refinement:
                needs_refinement = False
                logger.info("LLM refinement disabled by context")

            final_text = result.text

            needs_structuring = False
            show_draft = False
            emoji_level = 0

            if hasattr(self.transcription_router.strategy, "requires_structuring"):
                strategy = self.transcription_router.strategy
                needs_structuring = strategy.requires_structuring(request.duration_seconds)

                if needs_structuring:
                    show_draft = strategy.should_show_draft(request.duration_seconds)
                    emoji_level = strategy.get_emoji_level()
                    logger.info(
                        f"StructureStrategy: needs_structuring={needs_structuring}, "
                        f"show_draft={show_draft}, emoji_level={emoji_level}"
                    )

            if needs_structuring and self.text_processor:
                try:
                    final_text, llm_time = await self._apply_structuring(
                        request, result, show_draft, emoji_level
                    )
                    await self._send_result_and_update_state(
                        request,
                        final_text,
                        result,
                        active_mode="structured",
                        emoji_level=emoji_level,
                    )
                except Exception as e:
                    logger.error(f"Structuring failed: {e}", exc_info=True)

                    logger.warning("Falling back to original text")
                    final_text = result.text

                    if show_draft:
                        for msg in request.draft_messages:
                            try:
                                await msg.delete()
                            except Exception:
                                pass

                    try:
                        await request.status_message.delete()
                    except Exception:
                        pass

                    await self._send_result_and_update_state(
                        request,
                        result.text + "\n\nℹ️ (структурирование недоступно)",
                        result,
                    )

            elif needs_refinement and self.llm_service:
                try:
                    final_text, llm_time = await self._apply_refinement(request, result)
                    await self._send_result_and_update_state(request, final_text, result)
                except Exception as e:
                    logger.error(f"LLM refinement failed: {e}")
                    draft_text = result.text
                    if request.draft_messages:
                        await request.user_message.reply_text(
                            "✅ Готово\n\nℹ️ (улучшение текста недоступно)"
                        )
                    else:
                        try:
                            await request.status_message.edit_text(
                                f"✅ Готово:\n\n{draft_text}\n\nℹ️ (улучшение текста недоступно)"
                            )
                        except Exception:
                            pass
                    final_text = draft_text
            else:
                try:
                    await request.status_message.delete()
                except Exception as e:
                    logger.warning(f"Failed to delete status message: {e}")

                final_text = result.text
                await self._send_result_and_update_state(request, result.text, result)

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

            self.audio_handler.cleanup_file(request.file_path)
            if processed_path != request.file_path:
                self.audio_handler.cleanup_file(processed_path)

            logger.info(
                f"Request {request.id} completed successfully "
                f"(duration={request.duration_seconds}s, "
                f"processing_time={result.processing_time:.2f}s)"
            )

            return result

        except Exception as e:
            await progress.stop()

            try:
                await request.status_message.edit_text(
                    "❌ Произошла ошибка при обработке. Пожалуйста, попробуйте еще раз."
                )
            except Exception:
                pass

            self.audio_handler.cleanup_file(request.file_path)
            if processed_path != request.file_path:
                self.audio_handler.cleanup_file(processed_path)

            logger.error(f"Request {request.id} failed: {e}", exc_info=True)
            raise
