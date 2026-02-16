"""Integration tests for the full transcription pipeline.

Tests exercise multiple real components together, mocking only external
boundaries (Telegram API, Whisper API, DeepSeek API).
"""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.services.queue_manager import QueueManager, TranscriptionRequest
from src.services.transcription_orchestrator import TranscriptionOrchestrator
from src.services.text_processor import TextProcessor
from src.storage.repositories import (
    TranscriptionSegmentRepository,
    TranscriptionStateRepository,
    TranscriptionVariantRepository,
    UsageRepository,
    UserRepository,
)
from src.transcription.models import (
    TranscriptionContext,
    TranscriptionResult,
    TranscriptionSegment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_get_session(async_session):
    """Mock get_session to return test async_session everywhere it is imported."""

    @asynccontextmanager
    async def _get_session():
        yield async_session

    with (
        patch("src.services.transcription_orchestrator.get_session", _get_session),
        patch("src.bot.handlers.get_session", _get_session),
        patch("src.bot.retranscribe_handlers.get_session", _get_session),
    ):
        yield async_session


@pytest_asyncio.fixture
async def user_and_usage(async_session):
    """Create a real User + Usage in the test DB."""
    user_repo = UserRepository(async_session)
    usage_repo = UsageRepository(async_session)

    user = await user_repo.create(telegram_id=100500, username="tester")
    usage = await usage_repo.create(
        user_id=user.id,
        voice_file_id="test_voice_file_id",
        voice_duration_seconds=30,
    )
    await async_session.commit()
    return user, usage


@pytest_asyncio.fixture
async def repos(async_session):
    """Return a dict of real repository instances for the test session."""
    return {
        "user": UserRepository(async_session),
        "usage": UsageRepository(async_session),
        "state": TranscriptionStateRepository(async_session),
        "variant": TranscriptionVariantRepository(async_session),
        "segment": TranscriptionSegmentRepository(async_session),
    }


def _make_telegram_message(message_id: int = 1, chat_id: int = 200) -> MagicMock:
    """Create a mock Telegram Message with required methods."""
    msg = MagicMock()
    msg.message_id = message_id
    msg.chat_id = chat_id
    msg.reply_text = AsyncMock(return_value=MagicMock(message_id=message_id + 100))
    msg.reply_document = AsyncMock(return_value=MagicMock(message_id=message_id + 200))
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
    return msg


def _make_transcription_request(
    usage_id: int,
    file_path: Path | None = None,
    duration: int = 30,
    user_id: int = 100500,
) -> TranscriptionRequest:
    """Build a TranscriptionRequest with mocked Telegram objects."""
    return TranscriptionRequest(
        id="test-request-1",
        user_id=user_id,
        file_path=file_path or Path("/tmp/test_audio.ogg"),
        duration_seconds=duration,
        context=TranscriptionContext(user_id=user_id, duration_seconds=duration),
        status_message=_make_telegram_message(2),
        user_message=_make_telegram_message(1),
        usage_id=usage_id,
    )


def _make_transcription_result(text: str = "Test transcription text") -> TranscriptionResult:
    """Build a TranscriptionResult for tests."""
    return TranscriptionResult(
        text=text,
        language="ru",
        processing_time=1.5,
        audio_duration=30.0,
        provider_used="openai",
        model_name="whisper-1",
        segments=[
            TranscriptionSegment(start=0.0, end=10.0, text="First segment"),
            TranscriptionSegment(start=10.0, end=20.0, text="Second segment"),
            TranscriptionSegment(start=20.0, end=30.0, text="Third segment"),
        ],
    )


# ---------------------------------------------------------------------------
# 1. TranscriptionOrchestrator with real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_creates_usage_state_and_variants(
    async_session, mock_get_session, user_and_usage, repos
):
    """Orchestrator.process_transcription saves state, original variant, and
    updates usage in the real DB when no structuring/refinement is needed."""

    user, usage = user_and_usage
    result = _make_transcription_result()

    router = MagicMock()
    router.transcribe = AsyncMock(return_value=result)
    router.strategy = MagicMock(spec=[])  # no requires_structuring / HybridStrategy
    router.get_active_provider_name = MagicMock(return_value="openai")
    router.get_active_provider_model = MagicMock(return_value="whisper-1")

    audio_handler = MagicMock()
    audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
    audio_handler.cleanup_file = MagicMock()

    orchestrator = TranscriptionOrchestrator(
        transcription_router=router,
        audio_handler=audio_handler,
    )

    request = _make_transcription_request(usage.id, user_id=user.telegram_id)

    with patch("src.services.transcription_orchestrator.settings") as mock_settings:
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = True
        mock_settings.timestamps_min_duration = 5
        mock_settings.file_threshold_chars = 3000
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 10

        returned_result = await orchestrator.process_transcription(request)

    assert returned_result.text == result.text

    # Verify state was created in DB
    state = await repos["state"].get_by_usage_id(usage.id)
    assert state is not None
    assert state.active_mode == "original"

    # Verify original variant was saved
    variant = await repos["variant"].get_variant(usage_id=usage.id, mode="original")
    assert variant is not None
    assert "Test transcription text" in variant.text_content

    # Verify segments were saved (audio_duration=30 >= timestamps_min_duration=5)
    segments = await repos["segment"].get_by_usage_id(usage.id)
    assert len(segments) == 3


# ---------------------------------------------------------------------------
# 2. CallbackHandlers mode switching with real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_mode_switch_generates_and_caches_variant(
    async_session, mock_get_session, user_and_usage, repos
):
    """Switching to 'structured' mode generates the variant through LLM,
    stores it in real DB, and updates TranscriptionState."""

    user, usage = user_and_usage

    # Seed original variant and state
    await repos["variant"].create(
        usage_id=usage.id,
        mode="original",
        text_content="Raw transcription text from whisper",
        generated_by="transcription",
    )
    await repos["state"].create(
        usage_id=usage.id,
        message_id=100,
        chat_id=200,
    )
    await async_session.commit()

    # Build CallbackHandlers with real repos + mocked text processor
    text_processor = MagicMock(spec=TextProcessor)
    text_processor.create_structured = AsyncMock(return_value="<b>Structured</b> output")

    from src.bot.callbacks import CallbackHandlers

    handler = CallbackHandlers(
        state_repo=repos["state"],
        variant_repo=repos["variant"],
        segment_repo=repos["segment"],
        usage_repo=repos["usage"],
        text_processor=text_processor,
        user_repo=repos["user"],
    )

    # Build mock CallbackQuery
    query = MagicMock()
    query.data = f"mode:{usage.id}:mode=structured"
    query.from_user = MagicMock(id=user.telegram_id)
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock(chat_id=200, message_id=100)

    update = MagicMock()
    update.callback_query = query
    context = MagicMock()

    with patch("src.bot.callbacks.settings") as s:
        s.interactive_mode_enabled = True
        s.enable_structured_mode = True
        s.enable_summary_mode = True
        s.enable_magic_mode = True
        s.enable_emoji_option = False
        s.enable_timestamps_option = False
        s.enable_length_variations = False
        s.enable_retranscribe = False
        s.llm_processing_duration = 30
        s.progress_update_interval = 10
        s.llm_model = "deepseek-chat"
        s.file_threshold_chars = 3000
        s.max_cached_variants_per_transcription = 10
        s.progress_global_rate_limit = 0.5

        await handler.handle_mode_change(update, context)

    # Verify LLM was called
    text_processor.create_structured.assert_awaited_once()

    # Verify structured variant is in DB
    structured = await repos["variant"].get_variant(
        usage_id=usage.id, mode="structured", emoji_level=1
    )
    assert structured is not None
    assert "Structured" in structured.text_content

    # Verify state was updated
    updated_state = await repos["state"].get_by_usage_id(usage.id)
    assert updated_state is not None
    assert updated_state.active_mode == "structured"


# ---------------------------------------------------------------------------
# 3. Queue -> Orchestrator pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_enqueue_and_process(async_session, mock_get_session, user_and_usage, repos):
    """Enqueue a request, let QueueManager process it through a real
    TranscriptionOrchestrator, and verify result is stored."""

    user, usage = user_and_usage
    result = _make_transcription_result()

    router = MagicMock()
    router.transcribe = AsyncMock(return_value=result)
    router.strategy = MagicMock(spec=[])
    router.get_active_provider_name = MagicMock(return_value="openai")
    router.get_active_provider_model = MagicMock(return_value="whisper-1")

    audio_handler = MagicMock()
    audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test.ogg"))
    audio_handler.cleanup_file = MagicMock()

    orchestrator = TranscriptionOrchestrator(
        transcription_router=router, audio_handler=audio_handler
    )

    queue = QueueManager(max_queue_size=10, max_concurrent=1)

    with patch("src.services.transcription_orchestrator.settings") as s:
        s.interactive_mode_enabled = False
        s.audio_convert_to_mono = False
        s.audio_speed_multiplier = 1.0
        s.enable_retranscribe = False
        s.file_threshold_chars = 3000
        s.progress_rtf = 0.3
        s.progress_update_interval = 10

        await queue.start_worker(orchestrator.process_transcription)

        request = _make_transcription_request(usage.id, user_id=user.telegram_id)
        await queue.enqueue(request)

        # Wait for result
        response = await queue.wait_for_result(request.id, timeout=10.0, poll_interval=0.1)

    await queue.stop_worker()

    assert response.error is None
    assert response.result is not None
    assert response.result.text == result.text


# ---------------------------------------------------------------------------
# 4. Error recovery pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_sends_error_on_transcription_failure(
    async_session, mock_get_session, user_and_usage
):
    """When transcription fails, orchestrator sends an error message
    to the user and re-raises the exception."""

    user, usage = user_and_usage

    router = MagicMock()
    router.transcribe = AsyncMock(side_effect=RuntimeError("Whisper crashed"))
    router.get_active_provider_name = MagicMock(return_value="openai")
    router.get_active_provider_model = MagicMock(return_value="whisper-1")

    audio_handler = MagicMock()
    audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test.ogg"))
    audio_handler.cleanup_file = MagicMock()

    orchestrator = TranscriptionOrchestrator(
        transcription_router=router, audio_handler=audio_handler
    )

    request = _make_transcription_request(usage.id, user_id=user.telegram_id)

    with patch("src.services.transcription_orchestrator.settings") as s:
        s.audio_convert_to_mono = False
        s.audio_speed_multiplier = 1.0
        s.enable_retranscribe = False
        s.progress_rtf = 0.3
        s.progress_update_interval = 10

        with pytest.raises(RuntimeError, match="Whisper crashed"):
            await orchestrator.process_transcription(request)

    # Verify error message was sent to user
    request.status_message.edit_text.assert_awaited_with(
        "❌ Произошла ошибка при обработке. Пожалуйста, попробуйте еще раз."
    )
    audio_handler.cleanup_file.assert_called()


@pytest.mark.asyncio
async def test_structuring_failure_falls_back_to_original(
    async_session, mock_get_session, user_and_usage, repos
):
    """When structuring (LLM) fails, orchestrator falls back to original
    transcription text and sends it to the user."""

    user, usage = user_and_usage
    result = _make_transcription_result("Raw text from whisper")

    router = MagicMock()
    router.transcribe = AsyncMock(return_value=result)
    router.strategy = MagicMock()
    router.strategy.requires_structuring = MagicMock(return_value=True)
    router.strategy.should_show_draft = MagicMock(return_value=False)
    router.strategy.get_emoji_level = MagicMock(return_value=1)
    router.get_active_provider_name = MagicMock(return_value="openai")
    router.get_active_provider_model = MagicMock(return_value="whisper-1")

    audio_handler = MagicMock()
    audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test.ogg"))
    audio_handler.cleanup_file = MagicMock()

    text_processor = MagicMock(spec=TextProcessor)
    text_processor.create_structured = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    orchestrator = TranscriptionOrchestrator(
        transcription_router=router,
        audio_handler=audio_handler,
        text_processor=text_processor,
    )

    request = _make_transcription_request(usage.id, user_id=user.telegram_id)

    with patch("src.services.transcription_orchestrator.settings") as s:
        s.interactive_mode_enabled = True
        s.enable_timestamps_option = False
        s.timestamps_min_duration = 300
        s.file_threshold_chars = 3000
        s.audio_convert_to_mono = False
        s.audio_speed_multiplier = 1.0
        s.enable_retranscribe = False
        s.progress_rtf = 0.3
        s.progress_update_interval = 10
        s.llm_model = "deepseek-chat"

        returned = await orchestrator.process_transcription(request)

    # Orchestrator should succeed (fallback path)
    assert returned.text == "Raw text from whisper"

    # The reply_text should have been called with fallback text containing
    # the "структурирование недоступно" notice
    calls = request.user_message.reply_text.call_args_list
    sent_texts = [str(c) for c in calls]
    assert any("структурирование недоступно" in t for t in sent_texts)


# ---------------------------------------------------------------------------
# 5. Variant caching — repeated mode switches use cached variants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_variant_caching_avoids_regeneration(
    async_session, mock_get_session, user_and_usage, repos
):
    """Switching to structured, back to original, then back to structured
    does NOT regenerate the structured variant (uses cache)."""

    user, usage = user_and_usage

    # Seed original variant, state, and pre-cached structured variant
    await repos["variant"].create(
        usage_id=usage.id,
        mode="original",
        text_content="Original text",
        generated_by="transcription",
    )
    await repos["variant"].create(
        usage_id=usage.id,
        mode="structured",
        text_content="<b>Structured</b> cached text",
        generated_by="llm",
        emoji_level=1,
    )
    await repos["state"].create(usage_id=usage.id, message_id=100, chat_id=200)
    await async_session.commit()

    text_processor = MagicMock(spec=TextProcessor)
    text_processor.create_structured = AsyncMock(return_value="Should not be called")

    from src.bot.callbacks import CallbackHandlers

    handler = CallbackHandlers(
        state_repo=repos["state"],
        variant_repo=repos["variant"],
        segment_repo=repos["segment"],
        usage_repo=repos["usage"],
        text_processor=text_processor,
        user_repo=repos["user"],
    )

    def _make_query(mode: str) -> tuple[MagicMock, MagicMock]:
        query = MagicMock()
        query.data = f"mode:{usage.id}:mode={mode}"
        query.from_user = MagicMock(id=user.telegram_id)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock(chat_id=200, message_id=100)
        upd = MagicMock()
        upd.callback_query = query
        return upd, MagicMock()

    with patch("src.bot.callbacks.settings") as s:
        s.interactive_mode_enabled = True
        s.enable_structured_mode = True
        s.enable_summary_mode = True
        s.enable_magic_mode = True
        s.enable_emoji_option = False
        s.enable_timestamps_option = False
        s.enable_length_variations = False
        s.enable_retranscribe = False
        s.file_threshold_chars = 3000
        s.max_cached_variants_per_transcription = 10
        s.progress_global_rate_limit = 0.5

        # Switch to structured (already cached)
        upd, ctx = _make_query("structured")
        await handler.handle_mode_change(upd, ctx)

        # Switch back to original
        upd, ctx = _make_query("original")
        await handler.handle_mode_change(upd, ctx)

        # Switch to structured again — should use cache
        upd, ctx = _make_query("structured")
        await handler.handle_mode_change(upd, ctx)

    # LLM should never have been called because variant was pre-cached
    text_processor.create_structured.assert_not_awaited()

    # State should end up in structured mode
    final_state = await repos["state"].get_by_usage_id(usage.id)
    assert final_state is not None
    assert final_state.active_mode == "structured"


# ---------------------------------------------------------------------------
# 6. Timestamps integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timestamps_toggle_with_real_segments(
    async_session, mock_get_session, user_and_usage, repos
):
    """Toggle timestamps on with real segments in DB, verify formatted text,
    toggle off, verify base text restored."""

    user, usage = user_and_usage

    # Seed data: original variant, state, and segments
    await repos["variant"].create(
        usage_id=usage.id,
        mode="original",
        text_content="Base original text without timestamps",
        generated_by="transcription",
    )
    await repos["state"].create(usage_id=usage.id, message_id=100, chat_id=200)

    segments_data = [
        (0, 0.0, 10.0, "First segment"),
        (1, 10.0, 20.0, "Second segment"),
        (2, 20.0, 30.0, "Third segment"),
    ]
    await repos["segment"].create_batch(usage.id, segments_data)
    await async_session.commit()

    text_processor = MagicMock(spec=TextProcessor)
    text_processor.format_with_timestamps = MagicMock(
        return_value="[00:00] First segment\n[00:10] Second segment\n[00:20] Third segment"
    )

    from src.bot.callbacks import CallbackHandlers

    handler = CallbackHandlers(
        state_repo=repos["state"],
        variant_repo=repos["variant"],
        segment_repo=repos["segment"],
        usage_repo=repos["usage"],
        text_processor=text_processor,
        user_repo=repos["user"],
    )

    def _make_ts_query() -> tuple[MagicMock, MagicMock]:
        query = MagicMock()
        query.data = f"timestamps:{usage.id}"
        query.from_user = MagicMock(id=user.telegram_id)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock(chat_id=200, message_id=100)
        upd = MagicMock()
        upd.callback_query = query
        return upd, MagicMock()

    with patch("src.bot.callbacks.settings") as s:
        s.enable_timestamps_option = True
        s.enable_retranscribe = False
        s.file_threshold_chars = 3000
        s.interactive_mode_enabled = True
        s.enable_structured_mode = False
        s.enable_summary_mode = False
        s.enable_magic_mode = False
        s.enable_emoji_option = False
        s.enable_length_variations = False
        s.max_cached_variants_per_transcription = 10
        s.progress_global_rate_limit = 0.5

        # Toggle ON
        upd, ctx = _make_ts_query()
        await handler.handle_timestamps_toggle(upd, ctx)

    # State should have timestamps_enabled=True
    state = await repos["state"].get_by_usage_id(usage.id)
    assert state is not None
    assert state.timestamps_enabled is True

    # A timestamped variant should exist in DB
    ts_variant = await repos["variant"].get_variant(
        usage_id=usage.id, mode="original", timestamps_enabled=True
    )
    assert ts_variant is not None
    assert "[00:00]" in ts_variant.text_content

    with patch("src.bot.callbacks.settings") as s:
        s.enable_timestamps_option = True
        s.enable_retranscribe = False
        s.file_threshold_chars = 3000
        s.interactive_mode_enabled = True
        s.enable_structured_mode = False
        s.enable_summary_mode = False
        s.enable_magic_mode = False
        s.enable_emoji_option = False
        s.enable_length_variations = False
        s.max_cached_variants_per_transcription = 10
        s.progress_global_rate_limit = 0.5

        # Toggle OFF
        upd, ctx = _make_ts_query()
        await handler.handle_timestamps_toggle(upd, ctx)

    state = await repos["state"].get_by_usage_id(usage.id)
    assert state is not None
    assert state.timestamps_enabled is False


# ---------------------------------------------------------------------------
# 7. Queue error forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_forwards_worker_error_to_response(
    async_session, mock_get_session, user_and_usage
):
    """When the orchestrator callback raises, QueueManager captures the error
    in TranscriptionResponse.error."""

    user, usage = user_and_usage

    async def _failing_worker(request: TranscriptionRequest) -> TranscriptionResult:
        raise RuntimeError("Worker exploded")

    queue = QueueManager(max_queue_size=5, max_concurrent=1)
    await queue.start_worker(_failing_worker)

    request = _make_transcription_request(usage.id, user_id=user.telegram_id)
    await queue.enqueue(request)

    response = await queue.wait_for_result(request.id, timeout=10.0, poll_interval=0.1)
    await queue.stop_worker()

    assert response.result is None
    assert response.error is not None
    assert "Worker exploded" in response.error


# ---------------------------------------------------------------------------
# 8. Callback IDOR protection (integration-level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_idor_blocks_foreign_user(
    async_session, mock_get_session, user_and_usage, repos
):
    """A user pressing buttons on another user's transcription gets rejected
    via IDOR check with real DB lookup."""

    user, usage = user_and_usage

    await repos["variant"].create(
        usage_id=usage.id,
        mode="original",
        text_content="Some text",
        generated_by="transcription",
    )
    await repos["state"].create(usage_id=usage.id, message_id=100, chat_id=200)
    await async_session.commit()

    from src.bot.callbacks import CallbackHandlers

    handler = CallbackHandlers(
        state_repo=repos["state"],
        variant_repo=repos["variant"],
        segment_repo=repos["segment"],
        usage_repo=repos["usage"],
        text_processor=None,
        user_repo=repos["user"],
    )

    query = MagicMock()
    query.data = f"mode:{usage.id}:mode=structured"
    query.from_user = MagicMock(id=999999)  # Foreign user
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query

    with patch("src.bot.callbacks.settings") as s:
        s.interactive_mode_enabled = True
        s.enable_structured_mode = True
        s.enable_summary_mode = True
        s.enable_magic_mode = True
        s.enable_emoji_option = False
        s.enable_timestamps_option = False
        s.enable_length_variations = False
        s.enable_retranscribe = False

        await handler.handle_callback_query(update, MagicMock())

    # The foreign user should receive "access denied"
    query.answer.assert_any_await("Доступ запрещён", show_alert=True)


# ---------------------------------------------------------------------------
# 9. Multiple variants do not exceed limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_variant_limit_prevents_creation(
    async_session, mock_get_session, user_and_usage, repos
):
    """When the variant count reaches max_cached_variants_per_transcription,
    the CallbackHandler refuses to generate more."""

    user, usage = user_and_usage

    # Seed original variant and state
    await repos["variant"].create(
        usage_id=usage.id,
        mode="original",
        text_content="Original text",
        generated_by="transcription",
    )
    await repos["state"].create(usage_id=usage.id, message_id=100, chat_id=200)

    # Fill up to the limit with dummy variants
    limit = 3
    for i in range(limit - 1):  # -1 because original already counts
        await repos["variant"].create(
            usage_id=usage.id,
            mode="structured",
            text_content=f"Variant {i}",
            length_level=f"level_{i}",
            generated_by="llm",
        )
    await async_session.commit()

    text_processor = MagicMock(spec=TextProcessor)
    text_processor.create_structured = AsyncMock(return_value="Generated but should be rejected")

    from src.bot.callbacks import CallbackHandlers

    handler = CallbackHandlers(
        state_repo=repos["state"],
        variant_repo=repos["variant"],
        segment_repo=repos["segment"],
        usage_repo=repos["usage"],
        text_processor=text_processor,
        user_repo=repos["user"],
    )

    query = MagicMock()
    query.data = f"mode:{usage.id}:mode=summary"
    query.from_user = MagicMock(id=user.telegram_id)
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock(chat_id=200, message_id=100)

    update = MagicMock()
    update.callback_query = query

    with patch("src.bot.callbacks.settings") as s:
        s.interactive_mode_enabled = True
        s.enable_structured_mode = True
        s.enable_summary_mode = True
        s.enable_magic_mode = True
        s.enable_emoji_option = False
        s.enable_timestamps_option = False
        s.enable_length_variations = False
        s.enable_retranscribe = False
        s.llm_processing_duration = 30
        s.progress_update_interval = 10
        s.llm_model = "deepseek-chat"
        s.file_threshold_chars = 3000
        s.max_cached_variants_per_transcription = limit
        s.progress_global_rate_limit = 0.5

        await handler.handle_mode_change(update, MagicMock())

    # Verify the variant limit message was shown
    query.answer.assert_any_await("Достигнут лимит вариантов", show_alert=True)

    # No new variant should have been created
    all_variants = await repos["variant"].get_by_usage_id(usage.id)
    assert len(all_variants) == limit


# ---------------------------------------------------------------------------
# 10. Full round-trip: enqueue -> process -> interactive state ready
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_roundtrip_queue_to_interactive_state(
    async_session, mock_get_session, user_and_usage, repos
):
    """End-to-end: enqueue request, process through orchestrator, verify
    interactive state and variant are ready for callback handlers."""

    user, usage = user_and_usage
    result = _make_transcription_result("Full roundtrip text")

    router = MagicMock()
    router.transcribe = AsyncMock(return_value=result)
    router.strategy = MagicMock(spec=[])
    router.get_active_provider_name = MagicMock(return_value="openai")
    router.get_active_provider_model = MagicMock(return_value="whisper-1")

    audio_handler = MagicMock()
    audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test.ogg"))
    audio_handler.cleanup_file = MagicMock()

    orchestrator = TranscriptionOrchestrator(
        transcription_router=router, audio_handler=audio_handler
    )

    queue = QueueManager(max_queue_size=10, max_concurrent=1)

    with patch("src.services.transcription_orchestrator.settings") as s:
        s.interactive_mode_enabled = True
        s.enable_timestamps_option = True
        s.timestamps_min_duration = 5
        s.file_threshold_chars = 3000
        s.audio_convert_to_mono = False
        s.audio_speed_multiplier = 1.0
        s.enable_retranscribe = False
        s.progress_rtf = 0.3
        s.progress_update_interval = 10

        await queue.start_worker(orchestrator.process_transcription)

        request = _make_transcription_request(usage.id, user_id=user.telegram_id)
        await queue.enqueue(request)
        response = await queue.wait_for_result(request.id, timeout=10.0, poll_interval=0.1)

    await queue.stop_worker()

    assert response.error is None

    # State + variant should be in DB, ready for callbacks
    state = await repos["state"].get_by_usage_id(usage.id)
    assert state is not None

    variant = await repos["variant"].get_variant(usage_id=usage.id, mode="original")
    assert variant is not None
    assert "Full roundtrip text" in variant.text_content

    segments = await repos["segment"].get_by_usage_id(usage.id)
    assert len(segments) == 3
