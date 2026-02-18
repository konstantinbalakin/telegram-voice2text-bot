"""Tests for CallbackHandlers from src/bot/callbacks.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.callbacks import CallbackHandlers, LEVEL_TRANSITIONS, MODE_LABELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query(data: str, from_user_id: int = 111) -> AsyncMock:
    """Create a mock CallbackQuery."""
    query = AsyncMock()
    query.data = data
    query.from_user = MagicMock()
    query.from_user.id = from_user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.chat_id = 1000
    return query


def _make_update(query: MagicMock) -> MagicMock:
    """Create a mock Update with a callback query."""
    update = MagicMock()
    update.callback_query = query
    return update


def _make_state(
    usage_id: int = 42,
    active_mode: str = "original",
    emoji_level: int = 0,
    length_level: str = "default",
    timestamps_enabled: bool = False,
    is_file_message: bool = False,
    file_message_id: int | None = None,
) -> MagicMock:
    """Create a mock TranscriptionState."""
    state = MagicMock()
    state.usage_id = usage_id
    state.active_mode = active_mode
    state.emoji_level = emoji_level
    state.length_level = length_level
    state.timestamps_enabled = timestamps_enabled
    state.is_file_message = is_file_message
    state.file_message_id = file_message_id
    return state


def _make_variant(text_content: str = "test text") -> MagicMock:
    """Create a mock TranscriptionVariant."""
    variant = MagicMock()
    variant.text_content = text_content
    return variant


def _make_usage(usage_id: int = 42, user_id: int = 1) -> MagicMock:
    """Create a mock Usage."""
    usage = MagicMock()
    usage.id = usage_id
    usage.user_id = user_id
    return usage


def _make_user(user_id: int = 1, telegram_id: int = 111) -> MagicMock:
    """Create a mock User."""
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    return user


@pytest.fixture
def repos():
    """Create mock repositories."""
    state_repo = AsyncMock()
    variant_repo = AsyncMock()
    segment_repo = AsyncMock()
    usage_repo = AsyncMock()
    user_repo = AsyncMock()
    return state_repo, variant_repo, segment_repo, usage_repo, user_repo


@pytest.fixture
def handler(repos):
    """Create a CallbackHandlers instance with mock repos."""
    state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
    return CallbackHandlers(
        state_repo=state_repo,
        variant_repo=variant_repo,
        segment_repo=segment_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
    )


@pytest.fixture
def handler_with_tp(repos):
    """Create a CallbackHandlers instance with a mock TextProcessor."""
    state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
    text_processor = AsyncMock()
    text_processor.create_structured = AsyncMock(return_value="structured result")
    text_processor.summarize_text = AsyncMock(return_value="summary result")
    text_processor.create_magic = AsyncMock(return_value="magic result")
    text_processor.adjust_length = AsyncMock(return_value="adjusted result")
    text_processor.add_emojis = AsyncMock(return_value="emoji result")
    text_processor.format_with_timestamps = MagicMock(return_value="timestamped result")
    return CallbackHandlers(
        state_repo=state_repo,
        variant_repo=variant_repo,
        segment_repo=segment_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
        text_processor=text_processor,
    )


def _default_settings_patch():
    """Return a patch for settings with all features enabled."""
    return patch(
        "src.bot.callbacks.settings",
        **{
            "enable_structured_mode": True,
            "enable_summary_mode": True,
            "enable_magic_mode": True,
            "enable_length_variations": True,
            "enable_emoji_option": True,
            "enable_timestamps_option": True,
            "llm_processing_duration": 10,
            "progress_update_interval": 2,
            "file_threshold_chars": 4096,
            "llm_model": "deepseek-chat",
            "max_cached_variants_per_transcription": 50,
        },
    )


# ===========================================================================
# 1. LEVEL_TRANSITIONS state machine
# ===========================================================================


class TestLevelTransitions:
    """Tests for LEVEL_TRANSITIONS constant."""

    def test_default_shorter_goes_to_short(self):
        assert LEVEL_TRANSITIONS["default"]["shorter"] == "short"

    def test_default_longer_goes_to_long(self):
        assert LEVEL_TRANSITIONS["default"]["longer"] == "long"

    def test_short_shorter_goes_to_shorter(self):
        assert LEVEL_TRANSITIONS["short"]["shorter"] == "shorter"

    def test_short_longer_goes_to_default(self):
        assert LEVEL_TRANSITIONS["short"]["longer"] == "default"

    def test_shorter_has_no_shorter(self):
        assert "shorter" not in LEVEL_TRANSITIONS["shorter"]

    def test_shorter_longer_goes_to_short(self):
        assert LEVEL_TRANSITIONS["shorter"]["longer"] == "short"

    def test_long_shorter_goes_to_default(self):
        assert LEVEL_TRANSITIONS["long"]["shorter"] == "default"

    def test_long_longer_goes_to_longer(self):
        assert LEVEL_TRANSITIONS["long"]["longer"] == "longer"

    def test_longer_has_no_longer(self):
        assert "longer" not in LEVEL_TRANSITIONS["longer"]

    def test_longer_shorter_goes_to_long(self):
        assert LEVEL_TRANSITIONS["longer"]["shorter"] == "long"

    def test_mode_labels_has_all_modes(self):
        assert set(MODE_LABELS.keys()) == {"original", "structured", "summary", "magic"}


# ===========================================================================
# 2. handle_callback_query — routing
# ===========================================================================


class TestHandleCallbackQueryRouting:
    """Tests for the main callback query router."""

    @pytest.mark.asyncio
    async def test_no_query_returns_early(self, handler):
        update = MagicMock()
        update.callback_query = None
        context = MagicMock()
        await handler.handle_callback_query(update, context)

    @pytest.mark.asyncio
    async def test_no_data_returns_early(self, handler):
        query = _make_query(data="")
        query.data = None
        update = _make_update(query)
        context = MagicMock()
        await handler.handle_callback_query(update, context)

    @pytest.mark.asyncio
    async def test_noop_acknowledged_and_returns(self, handler):
        query = _make_query(data="noop")
        update = _make_update(query)
        context = MagicMock()
        await handler.handle_callback_query(update, context)
        query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_callback_data(self, handler):
        query = _make_query(data="totally_invalid")
        update = _make_update(query)
        context = MagicMock()
        await handler.handle_callback_query(update, context)
        # Should answer with error
        assert any("Ошибка обработки" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_unknown_action(self, repos):
        """Unknown but valid-format action gets 'not implemented' message."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        # Setup IDOR pass
        usage = _make_usage()
        owner = _make_user()
        usage_repo.get_by_id = AsyncMock(return_value=usage)
        user_repo.get_by_id = AsyncMock(return_value=owner)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            user_repo=user_repo,
        )

        # "noop" is a valid action that short-circuits before routing,
        # so we need to patch decode_callback_data for an unknown action
        query = _make_query(data="back:42")
        update = _make_update(query)
        context = MagicMock()

        # Back action routes to handle_back; instead let's test with a truly unknown
        with patch(
            "src.bot.callbacks.decode_callback_data",
            return_value={"action": "unknown_xyz", "usage_id": 42},
        ):
            await handler.handle_callback_query(update, context)
        assert any("Функция пока не реализована" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_routes_to_mode_handler(self, repos):
        """Test that action='mode' routes to handle_mode_change."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        usage = _make_usage()
        owner = _make_user()
        usage_repo.get_by_id = AsyncMock(return_value=usage)
        user_repo.get_by_id = AsyncMock(return_value=owner)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            user_repo=user_repo,
        )
        handler.handle_mode_change = AsyncMock()

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_callback_query(update, context)
        handler.handle_mode_change.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_routes_to_length_handler(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        usage = _make_usage()
        owner = _make_user()
        usage_repo.get_by_id = AsyncMock(return_value=usage)
        user_repo.get_by_id = AsyncMock(return_value=owner)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            user_repo=user_repo,
        )
        handler.handle_length_change = AsyncMock()

        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_callback_query(update, context)
        handler.handle_length_change.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_routes_to_back_handler(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        usage = _make_usage()
        owner = _make_user()
        usage_repo.get_by_id = AsyncMock(return_value=usage)
        user_repo.get_by_id = AsyncMock(return_value=owner)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            user_repo=user_repo,
        )
        handler.handle_back = AsyncMock()

        query = _make_query(data="back:42")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_callback_query(update, context)
        handler.handle_back.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_retranscribe_without_bot_handlers(self, repos):
        """retranscribe action without bot_handlers returns error."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        usage = _make_usage()
        owner = _make_user()
        usage_repo.get_by_id = AsyncMock(return_value=usage)
        user_repo.get_by_id = AsyncMock(return_value=owner)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            user_repo=user_repo,
            bot_handlers=None,
        )

        query = _make_query(data="retranscribe:42")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_callback_query(update, context)
        assert any("Ретранскрипция недоступна" in str(c) for c in query.answer.call_args_list)


# ===========================================================================
# 3. handle_mode_change
# ===========================================================================


class TestHandleModeChange:
    """Tests for handle_mode_change handler."""

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    async def test_switch_to_original_uses_cached_variant(
        self, mock_keyboard, mock_sanitize, repos
    ):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="structured")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        original_variant = _make_variant("original text")
        # First call: get_variant for original with defaults -> returns variant
        variant_repo.get_variant = AsyncMock(return_value=original_variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=original")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_mode_change(update, context)

        # State should be updated to original mode
        assert state.active_mode == "original"
        state_repo.update.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_already_in_same_mode_noop(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="structured")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_mode_change(update, context)

        # No state update should happen
        state_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_structured_mode(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="original")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        with patch("src.bot.callbacks.settings") as mock_settings:
            mock_settings.enable_structured_mode = False
            await handler.handle_mode_change(update, context)

        assert any(
            "Структурированный режим отключен" in str(c) for c in query.answer.call_args_list
        )

    @pytest.mark.asyncio
    async def test_disabled_summary_mode(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="original")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=summary")
        update = _make_update(query)
        context = MagicMock()

        with patch("src.bot.callbacks.settings") as mock_settings:
            mock_settings.enable_structured_mode = True
            mock_settings.enable_summary_mode = False
            await handler.handle_mode_change(update, context)

        assert any("Режим резюме отключен" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_disabled_magic_mode(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="original")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=magic")
        update = _make_update(query)
        context = MagicMock()

        with patch("src.bot.callbacks.settings") as mock_settings:
            mock_settings.enable_structured_mode = True
            mock_settings.enable_summary_mode = True
            mock_settings.enable_magic_mode = False
            await handler.handle_mode_change(update, context)

        assert any("Magic режим отключен" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_no_text_processor_returns_error(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="original")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        # No cached variant, so generation needed
        variant_repo.get_variant = AsyncMock(return_value=None)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=None,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_mode_change(update, context)

        assert any("LLM отключен" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_original_variant_not_found(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="original")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        # No variant found at all
        variant_repo.get_variant = AsyncMock(return_value=None)

        text_processor = AsyncMock()
        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_mode_change(update, context)

        assert any("Исходный текст не найден" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_switch_to_structured_generates_variant(
        self, mock_progress_cls, mock_keyboard, mock_sanitize, repos
    ):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="original")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        original_variant = _make_variant("original text")

        # First call returns None (no cached structured variant)
        # Second call returns original variant
        variant_repo.get_variant = AsyncMock(side_effect=[None, original_variant])

        generated_variant = _make_variant("structured text")
        variant_repo.get_or_create_variant = AsyncMock(return_value=(generated_variant, True))
        variant_repo.count_by_usage_id = AsyncMock(return_value=1)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        # Progress tracker mock
        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.create_structured = AsyncMock(return_value="structured text")

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_mode_change(update, context)

        text_processor.create_structured.assert_called_once_with("original text")
        assert state.active_mode == "structured"

    @pytest.mark.asyncio
    async def test_state_resets_params_on_mode_switch(self, repos):
        """Switching modes resets emoji/length/timestamps to defaults."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(
            active_mode="original",
            emoji_level=2,
            length_level="short",
            timestamps_enabled=True,
        )
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        variant = _make_variant("structured text")
        variant_repo.get_variant = AsyncMock(return_value=variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        with (
            _default_settings_patch(),
            patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x),
            patch("src.bot.callbacks.create_transcription_keyboard"),
        ):
            await handler.handle_mode_change(update, context)

        # Structured mode defaults: emoji=1, length=default, timestamps=False
        assert state.emoji_level == 1
        assert state.length_level == "default"
        assert state.timestamps_enabled is False

    @pytest.mark.asyncio
    async def test_state_not_found(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        state_repo.get_by_usage_id = AsyncMock(return_value=None)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=structured")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_mode_change(update, context)
        assert any("Состояние не найдено" in str(c) for c in query.answer.call_args_list)


# ===========================================================================
# 4. handle_length_change
# ===========================================================================


class TestHandleLengthChange:
    """Tests for handle_length_change handler."""

    @pytest.mark.asyncio
    async def test_feature_disabled(self, handler, repos):
        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        with patch("src.bot.callbacks.settings") as mock_settings:
            mock_settings.enable_length_variations = False
            await handler.handle_length_change(update, context)

        assert any("Изменение длины отключено" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_boundary_cant_go_shorter_than_shorter(self, handler, repos):
        state_repo = repos[0]
        state = _make_state(length_level="shorter")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_length_change(update, context)

        assert any("Уже минимальная длина" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_boundary_cant_go_longer_than_longer(self, handler, repos):
        state_repo = repos[0]
        state = _make_state(length_level="longer")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        query = _make_query(data="length:42:direction=longer")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_length_change(update, context)

        assert any("Уже максимальная длина" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    async def test_valid_transition_with_cached_variant(self, mock_keyboard, mock_sanitize, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(length_level="default", active_mode="structured")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        variant = _make_variant("shorter text")
        variant_repo.get_variant = AsyncMock(return_value=variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_length_change(update, context)

        assert state.length_level == "short"
        state_repo.update.assert_called_once_with(state)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_variant_generation_on_cache_miss(
        self, mock_progress_cls, mock_keyboard, mock_sanitize, repos
    ):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(length_level="default", active_mode="structured")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        current_variant = _make_variant("current text")
        # First call: no cached variant for new level; second call: current variant
        variant_repo.get_variant = AsyncMock(side_effect=[None, current_variant])

        generated_variant = _make_variant("shorter text")
        variant_repo.create = AsyncMock(return_value=generated_variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.adjust_length = AsyncMock(return_value="shorter text")

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_length_change(update, context)

        text_processor.adjust_length.assert_called_once()
        assert state.length_level == "short"

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_error_recovery_restores_text(
        self, mock_progress_cls, mock_keyboard, mock_sanitize, repos
    ):
        """On generation error, current text is restored."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(length_level="default", active_mode="structured")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        current_variant = _make_variant("current text")
        variant_repo.get_variant = AsyncMock(side_effect=[None, current_variant])

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.adjust_length = AsyncMock(side_effect=Exception("LLM error"))

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_length_change(update, context)

        # Should restore the message with current text
        query.edit_message_text.assert_called()
        assert any("Не удалось изменить длину" in str(c) for c in query.answer.call_args_list)
        # State should NOT be updated since the error occurred
        state_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_text_processor(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(length_level="default")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant_repo.get_variant = AsyncMock(return_value=None)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=None,
        )

        query = _make_query(data="length:42:direction=shorter")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_length_change(update, context)

        assert any("LLM отключен" in str(c) for c in query.answer.call_args_list)


# ===========================================================================
# 5. handle_emoji_toggle
# ===========================================================================


class TestHandleEmojiToggle:
    """Tests for handle_emoji_toggle handler."""

    @pytest.mark.asyncio
    async def test_feature_disabled(self, handler, repos):
        query = _make_query(data="emoji:42:direction=few")
        update = _make_update(query)
        context = MagicMock()

        with patch("src.bot.callbacks.settings") as mock_settings:
            mock_settings.enable_emoji_option = False
            await handler.handle_emoji_toggle(update, context)

        assert any("Опция смайлов отключена" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_direction_few_sets_level_1(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(emoji_level=0)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        variant = _make_variant("emoji text")
        variant_repo.get_variant = AsyncMock(return_value=variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="emoji:42:direction=few")
        update = _make_update(query)
        context = MagicMock()

        with (
            _default_settings_patch(),
            patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x),
            patch("src.bot.callbacks.create_transcription_keyboard"),
        ):
            await handler.handle_emoji_toggle(update, context)

        assert state.emoji_level == 1

    @pytest.mark.asyncio
    async def test_direction_moderate_sets_level_2(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(emoji_level=0)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        variant = _make_variant("emoji text")
        variant_repo.get_variant = AsyncMock(return_value=variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="emoji:42:direction=moderate")
        update = _make_update(query)
        context = MagicMock()

        with (
            _default_settings_patch(),
            patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x),
            patch("src.bot.callbacks.create_transcription_keyboard"),
        ):
            await handler.handle_emoji_toggle(update, context)

        assert state.emoji_level == 2

    @pytest.mark.asyncio
    async def test_increase_at_max_boundary(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(emoji_level=3)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="emoji:42:direction=increase")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_emoji_toggle(update, context)

        assert any("Больше смайлов нельзя" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_decrease_at_min_boundary(self, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(emoji_level=0)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="emoji:42:direction=decrease")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_emoji_toggle(update, context)

        assert any("Смайлы уже убраны" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_source_variant_prefers_level_0_when_adding(
        self, mock_progress_cls, mock_keyboard, mock_sanitize, repos
    ):
        """When adding emojis, prefer clean (level 0) text as source."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(emoji_level=0)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        clean_variant = _make_variant("clean text")
        generated_variant = _make_variant("emoji text")

        # Call sequence:
        # 1. get_variant for new emoji level -> None (no cached)
        # 2. get_variant for level 0 source -> clean_variant
        variant_repo.get_variant = AsyncMock(side_effect=[None, clean_variant])
        variant_repo.create = AsyncMock(return_value=generated_variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.add_emojis = AsyncMock(return_value="emoji text")

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="emoji:42:direction=few")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_emoji_toggle(update, context)

        # add_emojis should be called with clean_variant text
        text_processor.add_emojis.assert_called_once_with("clean text", 1, current_level=0)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_error_recovery_restores_text(
        self, mock_progress_cls, mock_keyboard, mock_sanitize, repos
    ):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(emoji_level=1)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        current_variant = _make_variant("current text")
        # Calls: 1) new level -> None, 2) level 0 source -> None, 3) current level -> current_variant
        # Then during error recovery: 4) current level -> current_variant
        variant_repo.get_variant = AsyncMock(
            side_effect=[None, None, current_variant, current_variant]
        )

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.add_emojis = AsyncMock(side_effect=Exception("LLM error"))

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="emoji:42:direction=increase")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_emoji_toggle(update, context)

        assert any("Не удалось добавить смайлы" in str(c) for c in query.answer.call_args_list)
        # State should NOT be updated since the error occurred
        state_repo.update.assert_not_called()


# ===========================================================================
# 6. handle_timestamps_toggle
# ===========================================================================


class TestHandleTimestampsToggle:
    """Tests for handle_timestamps_toggle handler."""

    @pytest.mark.asyncio
    async def test_feature_disabled(self, handler):
        query = _make_query(data="timestamps:42")
        update = _make_update(query)
        context = MagicMock()

        with patch("src.bot.callbacks.settings") as mock_settings:
            mock_settings.enable_timestamps_option = False
            await handler.handle_timestamps_toggle(update, context)

        assert any("Опция таймкодов отключена" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_no_segments_returns_unavailable(self, handler, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(timestamps_enabled=False)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        query = _make_query(data="timestamps:42")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_timestamps_toggle(update, context)

        assert any("Таймкоды недоступны" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    async def test_enable_timestamps_generates_variant(self, mock_keyboard, mock_sanitize, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(timestamps_enabled=False)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        segments = [MagicMock(), MagicMock()]
        segment_repo.get_by_usage_id = AsyncMock(return_value=segments)

        base_variant = _make_variant("base text")
        # First: get base variant (timestamps_enabled=False) -> base_variant
        # Second: get variant with timestamps=True -> None (cache miss)
        variant_repo.get_variant = AsyncMock(side_effect=[base_variant, None])

        ts_variant = _make_variant("timestamped text")
        variant_repo.create = AsyncMock(return_value=ts_variant)

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        mock_keyboard.return_value = MagicMock()

        text_processor = MagicMock()
        text_processor.format_with_timestamps = MagicMock(return_value="timestamped text")

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        query = _make_query(data="timestamps:42")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_timestamps_toggle(update, context)

        text_processor.format_with_timestamps.assert_called_once()
        assert state.timestamps_enabled is True
        state_repo.update.assert_called_once_with(state)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    async def test_disable_timestamps_uses_base_variant(self, mock_keyboard, mock_sanitize, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(timestamps_enabled=True)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        segments = [MagicMock()]
        segment_repo.get_by_usage_id = AsyncMock(return_value=segments)

        base_variant = _make_variant("base text without timestamps")
        variant_repo.get_variant = AsyncMock(return_value=base_variant)

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        mock_keyboard.return_value = MagicMock()

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="timestamps:42")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_timestamps_toggle(update, context)

        assert state.timestamps_enabled is False
        state_repo.update.assert_called_once_with(state)


# ===========================================================================
# 7. handle_back
# ===========================================================================


class TestHandleBack:
    """Tests for handle_back handler."""

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    async def test_back_restores_keyboard(self, mock_keyboard, mock_sanitize, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(active_mode="structured")
        state_repo.get_by_usage_id = AsyncMock(return_value=state)

        variant = _make_variant("some text")
        variant_repo.get_variant = AsyncMock(return_value=variant)

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        expected_keyboard = MagicMock()
        mock_keyboard.return_value = expected_keyboard

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="back:42")
        update = _make_update(query)
        context = MagicMock()

        with _default_settings_patch():
            await handler.handle_back(update, context)

        mock_keyboard.assert_called_once()
        # State mode should remain unchanged (back doesn't change mode)
        assert state.active_mode == "structured"

    @pytest.mark.asyncio
    async def test_back_state_not_found(self, handler, repos):
        state_repo = repos[0]
        state_repo.get_by_usage_id = AsyncMock(return_value=None)

        query = _make_query(data="back:42")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_back(update, context)
        assert any("Состояние не найдено" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    async def test_back_variant_not_found(self, handler, repos):
        state_repo, variant_repo = repos[0], repos[1]

        state = _make_state()
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant_repo.get_variant = AsyncMock(return_value=None)

        handler.segment_repo = repos[2]
        repos[2].get_by_usage_id = AsyncMock(return_value=[])

        query = _make_query(data="back:42")
        update = _make_update(query)
        context = MagicMock()

        await handler.handle_back(update, context)
        assert any("Текст не найден" in str(c) for c in query.answer.call_args_list)


# ===========================================================================
# 8. _generate_variant
# ===========================================================================


class TestGenerateVariant:
    """Tests for _generate_variant private method."""

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_successful_structured_generation(self, mock_progress_cls, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.create_structured = AsyncMock(return_value="structured output")

        generated_variant = _make_variant("structured output")
        variant_repo.get_or_create_variant = AsyncMock(return_value=(generated_variant, True))
        variant_repo.count_by_usage_id = AsyncMock(return_value=1)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        state = _make_state()
        query = _make_query(data="mode:42:mode=structured")
        context = MagicMock()

        with _default_settings_patch():
            result = await handler._generate_variant(
                query=query,
                context=context,
                state=state,
                usage_id=42,
                mode="structured",
                original_text="original",
                emoji_level=0,
                length_level="default",
                timestamps_enabled=False,
            )

        assert result is not None
        assert result.text_content == "structured output"
        text_processor.create_structured.assert_called_once_with("original")
        mock_progress.start.assert_called_once()
        mock_progress.stop.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_successful_summary_generation(self, mock_progress_cls, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.summarize_text = AsyncMock(return_value="summary output")

        generated_variant = _make_variant("summary output")
        variant_repo.get_or_create_variant = AsyncMock(return_value=(generated_variant, True))
        variant_repo.count_by_usage_id = AsyncMock(return_value=1)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        state = _make_state()
        query = _make_query(data="mode:42:mode=summary")
        context = MagicMock()

        with _default_settings_patch():
            result = await handler._generate_variant(
                query=query,
                context=context,
                state=state,
                usage_id=42,
                mode="summary",
                original_text="original",
                emoji_level=0,
                length_level="default",
                timestamps_enabled=False,
            )

        assert result is not None
        text_processor.summarize_text.assert_called_once_with("original", length_level="default")

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_successful_magic_generation(self, mock_progress_cls, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.create_magic = AsyncMock(return_value="magic output")

        generated_variant = _make_variant("magic output")
        variant_repo.get_or_create_variant = AsyncMock(return_value=(generated_variant, True))
        variant_repo.count_by_usage_id = AsyncMock(return_value=1)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        state = _make_state()
        query = _make_query(data="mode:42:mode=magic")
        context = MagicMock()

        with _default_settings_patch():
            result = await handler._generate_variant(
                query=query,
                context=context,
                state=state,
                usage_id=42,
                mode="magic",
                original_text="original",
                emoji_level=0,
                length_level="default",
                timestamps_enabled=False,
            )

        assert result is not None
        text_processor.create_magic.assert_called_once_with("original")

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.bot.callbacks.create_transcription_keyboard")
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_error_recovery_restores_original(
        self, mock_progress_cls, mock_keyboard, mock_sanitize, repos
    ):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.create_structured = AsyncMock(side_effect=Exception("LLM error"))

        segment_repo.get_by_usage_id = AsyncMock(return_value=[])
        mock_keyboard.return_value = MagicMock()

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        state = _make_state()
        query = _make_query(data="mode:42:mode=structured")
        context = MagicMock()

        with _default_settings_patch():
            result = await handler._generate_variant(
                query=query,
                context=context,
                state=state,
                usage_id=42,
                mode="structured",
                original_text="original",
                emoji_level=0,
                length_level="default",
                timestamps_enabled=False,
            )

        assert result is None
        # Progress should be stopped even on error
        assert mock_progress.stop.call_count == 1
        # Error message shown
        assert any("Не удалось обработать текст" in str(c) for c in query.answer.call_args_list)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.ProgressTracker")
    async def test_variant_limit_reached(self, mock_progress_cls, repos):
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        mock_progress = AsyncMock()
        mock_progress_cls.return_value = mock_progress

        text_processor = AsyncMock()
        text_processor.create_structured = AsyncMock(return_value="structured output")

        # Variant limit reached
        variant_repo.count_by_usage_id = AsyncMock(return_value=999)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            text_processor=text_processor,
        )

        state = _make_state()
        query = _make_query(data="mode:42:mode=structured")
        context = MagicMock()

        with _default_settings_patch():
            result = await handler._generate_variant(
                query=query,
                context=context,
                state=state,
                usage_id=42,
                mode="structured",
                original_text="original",
                emoji_level=0,
                length_level="default",
                timestamps_enabled=False,
            )

        assert result is None
        assert any("Достигнут лимит вариантов" in str(c) for c in query.answer.call_args_list)


# ===========================================================================
# 9. _check_variant_limit
# ===========================================================================


class TestCheckVariantLimit:
    """Tests for _check_variant_limit method."""

    @pytest.mark.asyncio
    async def test_under_limit_returns_false(self, handler, repos):
        variant_repo = repos[1]
        variant_repo.count_by_usage_id = AsyncMock(return_value=5)

        with _default_settings_patch():
            result = await handler._check_variant_limit(42)

        assert result is False

    @pytest.mark.asyncio
    async def test_at_limit_returns_true(self, handler, repos):
        variant_repo = repos[1]
        variant_repo.count_by_usage_id = AsyncMock(return_value=50)

        with _default_settings_patch():
            result = await handler._check_variant_limit(42)

        assert result is True

    @pytest.mark.asyncio
    async def test_over_limit_returns_true(self, handler, repos):
        variant_repo = repos[1]
        variant_repo.count_by_usage_id = AsyncMock(return_value=100)

        with _default_settings_patch():
            result = await handler._check_variant_limit(42)

        assert result is True


# ===========================================================================
# 10. update_transcription_display
# ===========================================================================


class TestUpdateTranscriptionDisplay:
    """Tests for update_transcription_display method."""

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    async def test_text_to_text_short_stays_text(self, mock_sanitize, repos):
        """Short text message stays as text message."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(is_file_message=False, active_mode="original")
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=original")
        keyboard = MagicMock()
        short_text = "short text"

        with _default_settings_patch():
            await handler.update_transcription_display(
                query, MagicMock(), state, short_text, keyboard, state_repo
            )

        query.edit_message_text.assert_called_once_with(
            short_text, reply_markup=keyboard, parse_mode="MarkdownV2"
        )

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.create_file_object")
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    async def test_file_to_file_long_stays_file(self, mock_sanitize, mock_file_obj, repos):
        """Long file message stays as file message."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(is_file_message=True, file_message_id=999, active_mode="structured")
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=structured")
        keyboard = MagicMock()
        long_text = "x" * 5000  # exceeds file_threshold_chars (4096)

        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file_obj.return_value = (mock_file, "PDF")

        context = MagicMock()
        new_msg = MagicMock()
        new_msg.message_id = 1001
        context.bot.send_document = AsyncMock(return_value=new_msg)
        context.bot.delete_message = AsyncMock()

        with _default_settings_patch():
            await handler.update_transcription_display(
                query, context, state, long_text, keyboard, state_repo
            )

        # Old file should be deleted
        context.bot.delete_message.assert_called_once_with(1000, 999)
        # New file should be sent
        context.bot.send_document.assert_called_once()
        # file_message_id should be updated
        assert state.file_message_id == 1001
        state_repo.update.assert_called_once_with(state)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.create_file_object")
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    async def test_text_to_file_conversion(self, mock_sanitize, mock_file_obj, repos):
        """Text message becomes file message when text too long."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(is_file_message=False, active_mode="structured")
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=structured")
        keyboard = MagicMock()
        long_text = "x" * 5000

        mock_file = MagicMock()
        mock_file.name = "test.txt"
        mock_file_obj.return_value = (mock_file, "TXT")

        context = MagicMock()
        file_msg = MagicMock()
        file_msg.message_id = 1002
        context.bot.send_document = AsyncMock(return_value=file_msg)

        with _default_settings_patch():
            await handler.update_transcription_display(
                query, context, state, long_text, keyboard, state_repo
            )

        assert state.is_file_message is True
        assert state.file_message_id == 1002
        state_repo.update.assert_called_once_with(state)

    @pytest.mark.asyncio
    @patch("src.bot.callbacks.sanitize_markdown", side_effect=lambda x: x)
    async def test_file_to_text_conversion(self, mock_sanitize, repos):
        """File message becomes text message when text short enough."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

        state = _make_state(is_file_message=True, file_message_id=999, active_mode="original")
        usage_repo.get_by_id = AsyncMock(return_value=_make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)

        handler = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
        )

        query = _make_query(data="mode:42:mode=original")
        keyboard = MagicMock()
        short_text = "now short text"

        context = MagicMock()
        context.bot.delete_message = AsyncMock()

        with _default_settings_patch():
            await handler.update_transcription_display(
                query, context, state, short_text, keyboard, state_repo
            )

        # Old file should be deleted
        context.bot.delete_message.assert_called_once_with(1000, 999)
        # Message updated with text
        query.edit_message_text.assert_called_once_with(
            short_text, reply_markup=keyboard, parse_mode="MarkdownV2"
        )
        assert state.is_file_message is False
        assert state.file_message_id is None
        state_repo.update.assert_called_once_with(state)
