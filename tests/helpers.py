"""Shared test helpers for callback handler tests."""

from unittest.mock import AsyncMock, MagicMock


def make_query(data: str, from_user_id: int = 111) -> AsyncMock:
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


def make_update(query: MagicMock) -> MagicMock:
    """Create a mock Update with a callback query."""
    update = MagicMock()
    update.callback_query = query
    return update


def make_state(
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


def make_variant(text_content: str = "test text") -> MagicMock:
    """Create a mock TranscriptionVariant."""
    variant = MagicMock()
    variant.text_content = text_content
    return variant


def make_usage(usage_id: int = 42, user_id: int = 1) -> MagicMock:
    """Create a mock Usage."""
    usage = MagicMock()
    usage.id = usage_id
    usage.user_id = user_id
    return usage


def make_user(user_id: int = 1, telegram_id: int = 111) -> MagicMock:
    """Create a mock User."""
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    return user
