"""Tests for IDOR protection in callback query handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.callbacks import CallbackHandlers


def _make_query(data: str, from_user_id: int) -> MagicMock:
    """Create a mock CallbackQuery."""
    query = AsyncMock()
    query.data = data
    query.from_user = MagicMock()
    query.from_user.id = from_user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def _make_update(query: MagicMock) -> MagicMock:
    """Create a mock Update with a callback query."""
    update = MagicMock()
    update.callback_query = query
    return update


def _make_user(user_id: int, telegram_id: int) -> MagicMock:
    """Create a mock User object."""
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    return user


def _make_usage(usage_id: int, user_id: int) -> MagicMock:
    """Create a mock Usage object."""
    usage = MagicMock()
    usage.id = usage_id
    usage.user_id = user_id
    return usage


@pytest.fixture
def repos():
    """Create mock repositories."""
    state_repo = AsyncMock()
    variant_repo = AsyncMock()
    segment_repo = AsyncMock()
    usage_repo = AsyncMock()
    user_repo = AsyncMock()
    return state_repo, variant_repo, segment_repo, usage_repo, user_repo


@pytest.mark.asyncio
async def test_idor_blocked_for_wrong_user(repos):
    """Test that a user cannot access another user's transcription."""
    state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

    # Owner is telegram_id=111, attacker is telegram_id=999
    owner = _make_user(user_id=1, telegram_id=111)
    usage = _make_usage(usage_id=42, user_id=1)

    usage_repo.get_by_id = AsyncMock(return_value=usage)
    user_repo.get_by_id = AsyncMock(return_value=owner)

    handler = CallbackHandlers(
        state_repo=state_repo,
        variant_repo=variant_repo,
        segment_repo=segment_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
    )

    # Attacker (telegram_id=999) tries to access usage_id=42
    query = _make_query(data="mode:42:mode=structured", from_user_id=999)
    update = _make_update(query)
    context = MagicMock()

    await handler.handle_callback_query(update, context)

    # Should have answered with "Доступ запрещён"
    # The first call is the initial query.answer() acknowledgement,
    # the second is the IDOR block
    calls = query.answer.call_args_list
    assert any(
        call.args == ("Доступ запрещён",) or call.kwargs.get("show_alert") is True
        for call in calls
        if "Доступ запрещён" in str(call)
    ), f"Expected 'Доступ запрещён' in answer calls: {calls}"

    # Ensure no handler was called (state_repo.get_by_usage_id not called)
    state_repo.get_by_usage_id.assert_not_called()


@pytest.mark.asyncio
async def test_idor_allowed_for_correct_user(repos):
    """Test that the owner can access their own transcription."""
    state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

    owner = _make_user(user_id=1, telegram_id=111)
    usage = _make_usage(usage_id=42, user_id=1)

    usage_repo.get_by_id = AsyncMock(return_value=usage)
    user_repo.get_by_id = AsyncMock(return_value=owner)

    # State for the mode handler to find
    mock_state = MagicMock()
    mock_state.usage_id = 42
    mock_state.active_mode = "original"
    mock_state.emoji_level = 0
    mock_state.length_level = "default"
    mock_state.timestamps_enabled = False
    mock_state.is_file_message = False
    mock_state.file_message_id = None
    state_repo.get_by_usage_id = AsyncMock(return_value=mock_state)

    # Variant to return
    mock_variant = MagicMock()
    mock_variant.text_content = "test text"
    variant_repo.get_variant = AsyncMock(return_value=mock_variant)

    segment_repo.get_by_usage_id = AsyncMock(return_value=[])

    handler = CallbackHandlers(
        state_repo=state_repo,
        variant_repo=variant_repo,
        segment_repo=segment_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
    )

    # Owner (telegram_id=111) accesses their own usage_id=42
    query = _make_query(data="mode:42:mode=structured", from_user_id=111)
    # Need message for edit_message_text
    query.message = MagicMock()
    update = _make_update(query)
    context = MagicMock()

    # Mock settings for mode validation
    with patch("src.bot.callbacks.settings") as mock_settings:
        mock_settings.enable_structured_mode = True
        mock_settings.enable_summary_mode = True
        mock_settings.enable_magic_mode = True
        mock_settings.llm_processing_duration = 10
        mock_settings.progress_update_interval = 2
        mock_settings.file_threshold_chars = 4096

        await handler.handle_callback_query(update, context)

    # The handler should have proceeded to state_repo.get_by_usage_id
    state_repo.get_by_usage_id.assert_called_once_with(42)

    # Should NOT have answered "Доступ запрещён"
    for call in query.answer.call_args_list:
        assert "Доступ запрещён" not in str(call)


@pytest.mark.asyncio
async def test_idor_blocked_usage_not_found(repos):
    """Test that access is denied when usage record doesn't exist."""
    state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos

    usage_repo.get_by_id = AsyncMock(return_value=None)

    handler = CallbackHandlers(
        state_repo=state_repo,
        variant_repo=variant_repo,
        segment_repo=segment_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
    )

    query = _make_query(data="mode:99999:mode=structured", from_user_id=111)
    update = _make_update(query)
    context = MagicMock()

    await handler.handle_callback_query(update, context)

    # Should have answered with "Доступ запрещён"
    calls = query.answer.call_args_list
    assert any(
        "Доступ запрещён" in str(call) for call in calls
    ), f"Expected 'Доступ запрещён' in answer calls: {calls}"
