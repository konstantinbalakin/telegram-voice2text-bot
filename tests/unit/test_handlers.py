"""Unit tests for BotHandlers class from src/bot/handlers.py."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers import (
    BotHandlers,
    MediaInfo,
    format_wait_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handlers() -> BotHandlers:
    """Create BotHandlers bypassing __init__ (no worker started)."""
    return BotHandlers.__new__(BotHandlers)


def _make_handlers_full(
    telegram_client: object | None = None,
) -> BotHandlers:
    """Create BotHandlers with mocked dependencies via __init__.

    asyncio.create_task is patched to prevent the queue worker from starting.
    """
    router = MagicMock()
    audio = MagicMock()
    queue = MagicMock()
    orchestrator = MagicMock()

    with patch("asyncio.create_task"):
        h = BotHandlers(
            transcription_router=router,
            audio_handler=audio,
            queue_manager=queue,
            orchestrator=orchestrator,
            telegram_client=telegram_client,
        )
    return h


def _make_update(
    user_id: int = 100,
    username: str = "testuser",
    first_name: str = "Test",
    last_name: str = "User",
    message: MagicMock | None = None,
) -> MagicMock:
    """Create a mock Telegram Update object."""
    update = MagicMock()
    tg_user = MagicMock()
    tg_user.id = user_id
    tg_user.username = username
    tg_user.first_name = first_name
    tg_user.last_name = last_name
    update.effective_user = tg_user
    update.message = message or MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.message_id = 1
    update.message.chat_id = 1
    update.effective_message = update.message
    return update


def _make_context() -> MagicMock:
    """Create a mock Telegram context."""
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.get_file = AsyncMock()
    return ctx


def _make_db_user(
    user_id: int = 1,
    telegram_id: int = 100,
    daily_quota_seconds: int = 60,
    today_usage_seconds: int = 0,
    is_unlimited: bool = False,
    last_reset_date: date | None = None,
) -> MagicMock:
    """Create a mock database User."""
    u = MagicMock()
    u.id = user_id
    u.telegram_id = telegram_id
    u.daily_quota_seconds = daily_quota_seconds
    u.today_usage_seconds = today_usage_seconds
    u.is_unlimited = is_unlimited
    u.last_reset_date = last_reset_date or date.today()
    u.created_at = MagicMock()
    u.created_at.strftime = MagicMock(return_value="01.01.2025")
    return u


def _async_ctx_manager(return_value: object) -> MagicMock:
    """Create an async context manager mock that yields *return_value*."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# MediaInfo dataclass
# ---------------------------------------------------------------------------


class TestMediaInfo:
    """Tests for the MediaInfo dataclass."""

    def test_basic_construction(self) -> None:
        info = MediaInfo(
            file_id="file123",
            file_size=1024,
            duration_seconds=30,
            media_type="voice",
        )
        assert info.file_id == "file123"
        assert info.file_size == 1024
        assert info.duration_seconds == 30
        assert info.media_type == "voice"
        assert info.mime_type is None
        assert info.file_name is None

    def test_optional_fields(self) -> None:
        info = MediaInfo(
            file_id="f1",
            file_size=0,
            duration_seconds=None,
            media_type="document",
            mime_type="audio/mpeg",
            file_name="audio.mp3",
        )
        assert info.duration_seconds is None
        assert info.mime_type == "audio/mpeg"
        assert info.file_name == "audio.mp3"


# ---------------------------------------------------------------------------
# format_wait_time
# ---------------------------------------------------------------------------


class TestFormatWaitTime:
    """Tests for format_wait_time() function."""

    def test_zero_seconds(self) -> None:
        assert format_wait_time(0) == "~0с"

    def test_under_60(self) -> None:
        assert format_wait_time(45) == "~45с"

    def test_59_seconds(self) -> None:
        assert format_wait_time(59) == "~59с"

    def test_exactly_60(self) -> None:
        assert format_wait_time(60) == "~1м"

    def test_61_seconds(self) -> None:
        assert format_wait_time(61) == "~1м 1с"

    def test_120_seconds(self) -> None:
        assert format_wait_time(120) == "~2м"

    def test_3661_seconds(self) -> None:
        # 3661 = 61 min 1 sec
        assert format_wait_time(3661) == "~61м 1с"

    def test_float_input(self) -> None:
        # 90.7 → int(90.7)=90 → 1м 30с
        assert format_wait_time(90.7) == "~1м 30с"


# ---------------------------------------------------------------------------
# BotHandlers.__init__
# ---------------------------------------------------------------------------


class TestBotHandlersInit:
    """Tests for BotHandlers constructor."""

    def test_init_sets_callback_and_creates_task(self) -> None:
        router = MagicMock()
        audio = MagicMock()
        queue = MagicMock()
        orchestrator = MagicMock()

        with patch("asyncio.create_task") as mock_create:
            h = BotHandlers(
                transcription_router=router,
                audio_handler=audio,
                queue_manager=queue,
                orchestrator=orchestrator,
            )

        queue.set_on_queue_changed.assert_called_once_with(h._update_queue_messages)
        mock_create.assert_called_once()
        assert h.transcription_router is router
        assert h.audio_handler is audio
        assert h.queue_manager is queue
        assert h.orchestrator is orchestrator
        assert h.telegram_client is None

    def test_init_with_telegram_client(self) -> None:
        client = MagicMock()
        with patch("asyncio.create_task"):
            h = BotHandlers(
                transcription_router=MagicMock(),
                audio_handler=MagicMock(),
                queue_manager=MagicMock(),
                orchestrator=MagicMock(),
                telegram_client=client,
            )
        assert h.telegram_client is client


# ---------------------------------------------------------------------------
# _extract_media_info
# ---------------------------------------------------------------------------


class TestExtractMediaInfo:
    """Tests for BotHandlers._extract_media_info."""

    def test_voice_message(self) -> None:
        h = _make_handlers()
        update = MagicMock()
        update.message.voice.file_id = "voice_id"
        update.message.voice.file_size = 5000
        update.message.voice.duration = 10
        update.message.voice.file_name = None

        info = h._extract_media_info(update, "voice")

        assert info is not None
        assert info.file_id == "voice_id"
        assert info.duration_seconds == 10
        assert info.media_type == "voice"
        assert info.mime_type is None

    def test_audio_file(self) -> None:
        h = _make_handlers()
        update = MagicMock()
        update.message.audio.file_id = "audio_id"
        update.message.audio.file_size = 8000
        update.message.audio.duration = 120
        update.message.audio.file_name = "song.mp3"

        info = h._extract_media_info(update, "audio")

        assert info is not None
        assert info.file_id == "audio_id"
        assert info.duration_seconds == 120
        assert info.file_name == "song.mp3"

    def test_document_no_duration(self) -> None:
        h = _make_handlers()
        update = MagicMock()
        update.message.document.file_id = "doc_id"
        update.message.document.file_size = 3000
        update.message.document.mime_type = "audio/ogg"
        update.message.document.file_name = "rec.ogg"
        # document should not have duration field queried

        info = h._extract_media_info(update, "document")

        assert info is not None
        assert info.duration_seconds is None
        assert info.mime_type == "audio/ogg"
        assert info.media_type == "document"

    def test_video_timedelta_duration(self) -> None:
        h = _make_handlers()
        update = MagicMock()
        update.message.video.file_id = "vid_id"
        update.message.video.file_size = 50000
        update.message.video.duration = timedelta(seconds=90)
        update.message.video.file_name = "clip.mp4"

        info = h._extract_media_info(update, "video")

        assert info is not None
        assert info.duration_seconds == 90
        assert info.media_type == "video"

    def test_missing_message_returns_none(self) -> None:
        h = _make_handlers()
        update = MagicMock()
        update.message = None

        info = h._extract_media_info(update, "voice")
        assert info is None

    def test_missing_media_object_returns_none(self) -> None:
        h = _make_handlers()
        update = MagicMock()
        update.message.voice = None

        info = h._extract_media_info(update, "voice")
        assert info is None


# ---------------------------------------------------------------------------
# start_command
# ---------------------------------------------------------------------------


class TestStartCommand:
    """Tests for BotHandlers.start_command."""

    @pytest.mark.asyncio
    async def test_new_user_created(self) -> None:
        h = _make_handlers()
        update = _make_update()
        ctx = _make_context()

        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=None)
        mock_user_repo.create = AsyncMock()

        with (
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
        ):
            await h.start_command(update, ctx)

        mock_user_repo.create.assert_awaited_once()
        update.message.reply_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_user_no_create(self) -> None:
        h = _make_handlers()
        update = _make_update()
        ctx = _make_context()

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_user_repo.create = AsyncMock()

        with (
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
        ):
            await h.start_command(update, ctx)

        mock_user_repo.create.assert_not_awaited()
        update.message.reply_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_effective_user_returns_early(self) -> None:
        h = _make_handlers()
        update = _make_update()
        update.effective_user = None
        ctx = _make_context()

        await h.start_command(update, ctx)

        update.message.reply_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# help_command
# ---------------------------------------------------------------------------


class TestHelpCommand:
    """Tests for BotHandlers.help_command."""

    @pytest.mark.asyncio
    async def test_sends_help_text(self) -> None:
        h = _make_handlers()
        update = _make_update()
        ctx = _make_context()

        await h.help_command(update, ctx)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Как пользоваться ботом" in text


# ---------------------------------------------------------------------------
# stats_command
# ---------------------------------------------------------------------------


class TestStatsCommand:
    """Tests for BotHandlers.stats_command."""

    @pytest.mark.asyncio
    async def test_no_effective_user(self) -> None:
        h = _make_handlers()
        update = _make_update()
        update.effective_user = None
        ctx = _make_context()

        await h.stats_command(update, ctx)

        update.message.reply_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_not_found(self) -> None:
        h = _make_handlers()
        update = _make_update()
        ctx = _make_context()

        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=None)
        mock_usage_repo = MagicMock()

        with (
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            await h.stats_command(update, ctx)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "не найден" in text

    @pytest.mark.asyncio
    async def test_no_usages(self) -> None:
        h = _make_handlers()
        update = _make_update()
        ctx = _make_context()

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=0)

        with (
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            await h.stats_command(update, ctx)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "нет обработанных" in text

    @pytest.mark.asyncio
    async def test_with_stats(self) -> None:
        h = _make_handlers()
        update = _make_update()
        ctx = _make_context()

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=5)
        mock_usage_repo.get_user_total_duration = AsyncMock(return_value=150.0)

        with (
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            await h.stats_command(update, ctx)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "5 сообщений" in text
        assert "150.0 сек" in text


# ---------------------------------------------------------------------------
# voice / audio / document / video_message_handler (thin wrappers)
# ---------------------------------------------------------------------------


class TestMediaWrappers:
    """Tests that thin wrapper handlers delegate correctly."""

    @pytest.mark.asyncio
    async def test_voice_handler_delegates(self) -> None:
        h = _make_handlers()
        media_info = MediaInfo("f1", 100, 10, "voice")
        h._extract_media_info = MagicMock(return_value=media_info)
        h._handle_media_message = AsyncMock()
        update, ctx = _make_update(), _make_context()

        await h.voice_message_handler(update, ctx)

        h._extract_media_info.assert_called_once_with(update, "voice")
        h._handle_media_message.assert_awaited_once_with(update, ctx, media_info)

    @pytest.mark.asyncio
    async def test_audio_handler_delegates(self) -> None:
        h = _make_handlers()
        media_info = MediaInfo("f1", 100, 10, "audio")
        h._extract_media_info = MagicMock(return_value=media_info)
        h._handle_media_message = AsyncMock()
        update, ctx = _make_update(), _make_context()

        await h.audio_message_handler(update, ctx)

        h._extract_media_info.assert_called_once_with(update, "audio")
        h._handle_media_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_document_handler_delegates(self) -> None:
        h = _make_handlers()
        media_info = MediaInfo("f1", 100, None, "document", mime_type="audio/ogg")
        h._extract_media_info = MagicMock(return_value=media_info)
        h._handle_media_message = AsyncMock()
        update, ctx = _make_update(), _make_context()

        await h.document_message_handler(update, ctx)

        h._extract_media_info.assert_called_once_with(update, "document")
        h._handle_media_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_video_handler_delegates(self) -> None:
        h = _make_handlers()
        media_info = MediaInfo("f1", 100, 60, "video")
        h._extract_media_info = MagicMock(return_value=media_info)
        h._handle_media_message = AsyncMock()
        update, ctx = _make_update(), _make_context()

        await h.video_message_handler(update, ctx)

        h._extract_media_info.assert_called_once_with(update, "video")
        h._handle_media_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_voice_handler_none_media_info(self) -> None:
        h = _make_handlers()
        h._extract_media_info = MagicMock(return_value=None)
        h._handle_media_message = AsyncMock()
        update, ctx = _make_update(), _make_context()

        await h.voice_message_handler(update, ctx)

        h._handle_media_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_media_message
# ---------------------------------------------------------------------------


class TestHandleMediaMessage:
    """Tests for BotHandlers._handle_media_message."""

    def _setup_handler(self) -> BotHandlers:
        h = _make_handlers_full()
        h.queue_manager.get_queue_depth = MagicMock(return_value=0)
        h.queue_manager.enqueue = AsyncMock(return_value=1)
        h.queue_manager.get_processing_count = MagicMock(return_value=0)
        h.queue_manager.get_queue_position_by_id = MagicMock(return_value=1)
        h.queue_manager.get_estimated_wait_time_by_id = MagicMock(return_value=(10, 5))
        h.audio_handler.download_voice_message = AsyncMock(return_value="/tmp/test.ogg")
        h.audio_handler.temp_dir = "/tmp"
        h.transcription_router.strategy = MagicMock()
        h.transcription_router.strategy.is_benchmark_mode = MagicMock(return_value=False)
        return h

    @pytest.mark.asyncio
    async def test_unsupported_document_mime_ignored(self) -> None:
        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, None, "document", mime_type="application/pdf")

        with patch("src.bot.handlers.settings") as ms:
            ms.max_voice_duration_seconds = 300
            await h._handle_media_message(update, ctx, media_info)

        # Should not send any status message (reply_text for "Загружаю файл")
        # The function should return early without doing anything beyond logging
        update.message.reply_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duration_too_long_rejected(self) -> None:
        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 600, "voice")

        with patch("src.bot.handlers.settings") as ms:
            ms.max_voice_duration_seconds = 300
            await h._handle_media_message(update, ctx, media_info)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Максимальная длительность" in text

    @pytest.mark.asyncio
    async def test_queue_full_rejected(self) -> None:
        h = self._setup_handler()
        h.queue_manager.get_queue_depth = MagicMock(return_value=50)
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")

        with patch("src.bot.handlers.settings") as ms:
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            await h._handle_media_message(update, ctx, media_info)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Очередь переполнена" in text

    @pytest.mark.asyncio
    async def test_file_too_big_rejected(self) -> None:
        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        # 30 MB, limit is 20 MB, telethon disabled
        media_info = MediaInfo("f1", 30 * 1024 * 1024, 30, "voice")

        with patch("src.bot.handlers.settings") as ms:
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.telethon_enabled = False
            ms.max_file_size_bytes = 20 * 1024 * 1024
            await h._handle_media_message(update, ctx, media_info)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        assert "слишком большой" in text

    @pytest.mark.asyncio
    async def test_quota_exceeded_rejected(self) -> None:
        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")

        db_user = _make_db_user(today_usage_seconds=50, daily_quota_seconds=60)
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)

        with (
            patch("src.bot.handlers.settings") as ms,
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
        ):
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.max_file_size_bytes = 20 * 1024 * 1024
            ms.telethon_enabled = False
            ms.enable_quota_check = True
            await h._handle_media_message(update, ctx, media_info)

        update.message.reply_text.assert_awaited()
        text = update.message.reply_text.call_args[0][0]
        assert "дневной лимит" in text.lower() or "Достигнут дневной лимит" in text

    @pytest.mark.asyncio
    async def test_successful_enqueue(self) -> None:
        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")
        status_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage = MagicMock()
        mock_usage.id = 42
        mock_usage_repo.create = AsyncMock(return_value=mock_usage)
        mock_usage_repo.update = AsyncMock()

        telegram_file = MagicMock()
        ctx.bot.get_file = AsyncMock(return_value=telegram_file)

        with (
            patch("src.bot.handlers.settings") as ms,
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.max_file_size_bytes = 20 * 1024 * 1024
            ms.telethon_enabled = False
            ms.enable_quota_check = False
            ms.progress_rtf = 0.3
            await h._handle_media_message(update, ctx, media_info)

        h.queue_manager.enqueue.assert_awaited_once()
        # Status message should be edited (either "начинаю обработку" or queue position)
        status_msg.edit_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_bad_request_file_too_big(self) -> None:
        """BadRequest with 'File is too big' should show specific error."""
        from telegram.error import BadRequest

        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")
        status_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage = MagicMock()
        mock_usage.id = 1
        mock_usage_repo.create = AsyncMock(return_value=mock_usage)
        mock_usage_repo.update = AsyncMock()

        ctx.bot.get_file = AsyncMock(side_effect=BadRequest("File is too big"))

        with (
            patch("src.bot.handlers.settings") as ms,
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.max_file_size_bytes = 20 * 1024 * 1024
            ms.telethon_enabled = False
            ms.enable_quota_check = False
            await h._handle_media_message(update, ctx, media_info)

        status_msg.edit_text.assert_awaited()
        text = status_msg.edit_text.call_args[0][0]
        assert "слишком большой" in text

    @pytest.mark.asyncio
    async def test_generic_exception_shows_error(self) -> None:
        """Generic exception should show a generic error message."""
        h = self._setup_handler()
        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")
        status_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage = MagicMock()
        mock_usage.id = 1
        mock_usage_repo.create = AsyncMock(return_value=mock_usage)

        ctx.bot.get_file = AsyncMock(side_effect=RuntimeError("unexpected"))

        with (
            patch("src.bot.handlers.settings") as ms,
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.max_file_size_bytes = 20 * 1024 * 1024
            ms.telethon_enabled = False
            ms.enable_quota_check = False
            await h._handle_media_message(update, ctx, media_info)

        status_msg.edit_text.assert_awaited()
        text = status_msg.edit_text.call_args[0][0]
        assert "ошибка" in text.lower()

    @pytest.mark.asyncio
    async def test_client_api_download_path(self) -> None:
        """When file_size > max_file_size_bytes and telethon enabled, use client API."""
        client = MagicMock()
        client.download_large_file = AsyncMock(return_value="/tmp/large.ogg")

        h = _make_handlers_full(telegram_client=client)
        h.queue_manager.get_queue_depth = MagicMock(return_value=0)
        h.queue_manager.enqueue = AsyncMock(return_value=1)
        h.queue_manager.get_processing_count = MagicMock(return_value=0)
        h.audio_handler.download_voice_message = AsyncMock()
        h.audio_handler.temp_dir = "/tmp"
        h.transcription_router.strategy = MagicMock()
        h.transcription_router.strategy.is_benchmark_mode = MagicMock(return_value=False)

        update = _make_update()
        ctx = _make_context()
        # file_size > max_file_size_bytes (25 MB > 20 MB)
        media_info = MediaInfo("f1", 25 * 1024 * 1024, 30, "voice")
        status_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage = MagicMock()
        mock_usage.id = 1
        mock_usage_repo.create = AsyncMock(return_value=mock_usage)
        mock_usage_repo.update = AsyncMock()

        with (
            patch("src.bot.handlers.settings") as ms,
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.max_file_size_bytes = 20 * 1024 * 1024
            ms.telethon_enabled = True
            ms.enable_quota_check = False
            ms.progress_rtf = 0.3
            await h._handle_media_message(update, ctx, media_info)

        client.download_large_file.assert_awaited_once()
        h.audio_handler.download_voice_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_queue_full_exception(self) -> None:
        """asyncio.QueueFull during enqueue should show error and cleanup."""
        h = self._setup_handler()
        h.queue_manager.enqueue = AsyncMock(side_effect=asyncio.QueueFull())
        h.audio_handler.cleanup_file = MagicMock()

        update = _make_update()
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")
        status_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        db_user = _make_db_user()
        mock_session = MagicMock()
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_telegram_id = AsyncMock(return_value=db_user)
        mock_usage_repo = MagicMock()
        mock_usage = MagicMock()
        mock_usage.id = 1
        mock_usage_repo.create = AsyncMock(return_value=mock_usage)
        mock_usage_repo.update = AsyncMock()

        telegram_file = MagicMock()
        ctx.bot.get_file = AsyncMock(return_value=telegram_file)

        with (
            patch("src.bot.handlers.settings") as ms,
            patch("src.bot.handlers.get_session", return_value=_async_ctx_manager(mock_session)),
            patch("src.bot.handlers.UserRepository", return_value=mock_user_repo),
            patch("src.bot.handlers.UsageRepository", return_value=mock_usage_repo),
        ):
            ms.max_voice_duration_seconds = 300
            ms.max_queue_size = 50
            ms.max_file_size_bytes = 20 * 1024 * 1024
            ms.telethon_enabled = False
            ms.enable_quota_check = False
            ms.progress_rtf = 0.3
            await h._handle_media_message(update, ctx, media_info)

        status_msg.edit_text.assert_awaited()
        text = status_msg.edit_text.call_args[0][0]
        assert "переполнена" in text.lower()
        h.audio_handler.cleanup_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_user_or_message_returns_early(self) -> None:
        h = self._setup_handler()
        update = _make_update()
        update.effective_user = None
        ctx = _make_context()
        media_info = MediaInfo("f1", 100, 30, "voice")

        with patch("src.bot.handlers.settings"):
            await h._handle_media_message(update, ctx, media_info)

        update.message.reply_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# error_handler
# ---------------------------------------------------------------------------


class TestErrorHandler:
    """Tests for BotHandlers.error_handler."""

    @pytest.mark.asyncio
    async def test_logs_and_sends_message(self) -> None:
        from telegram import Update

        h = _make_handlers()
        update = MagicMock(spec=Update)
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        ctx = _make_context()
        ctx.error = RuntimeError("test error")

        await h.error_handler(update, ctx)

        update.effective_message.reply_text.assert_awaited_once()
        text = update.effective_message.reply_text.call_args[0][0]
        assert "ошибка" in text.lower()

    @pytest.mark.asyncio
    async def test_non_update_object(self) -> None:
        """When update is not an Update instance, no message is sent."""
        h = _make_handlers()
        ctx = _make_context()
        ctx.error = RuntimeError("test")

        # Pass a plain string — not an Update instance
        await h.error_handler("not-an-update", ctx)
        # Should not raise and should not call reply_text
