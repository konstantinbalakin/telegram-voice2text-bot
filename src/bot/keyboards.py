"""Keyboard manager for inline keyboards in interactive transcription."""

from typing import Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.storage.models import TranscriptionState
from src.config import Settings


def encode_callback_data(action: str, usage_id: int, **params: Any) -> str:
    """
    Encode callback data in compact format.

    Format: "action:usage_id:param1=val1,param2=val2"

    Args:
        action: Action type (mode, length, emoji, timestamps, etc.)
        usage_id: Usage record ID
        **params: Additional parameters

    Returns:
        Encoded callback data string (max 64 bytes)

    Raises:
        ValueError: If encoded data exceeds 64 bytes
    """
    parts = [action, str(usage_id)]
    if params:
        param_str = ",".join(f"{k}={v}" for k, v in params.items())
        parts.append(param_str)

    result = ":".join(parts)

    # Check Telegram's 64-byte limit
    if len(result.encode("utf-8")) > 64:
        raise ValueError(f"Callback data too long: {len(result)} bytes (max 64)")

    return result


_VALID_ACTIONS = frozenset(
    [
        "mode",
        "length",
        "emoji",
        "timestamps",
        "retranscribe_menu",
        "retranscribe",
        "back",
        "noop",
        "download",
        "download_fmt",
    ]
)

_VALID_MODES = frozenset(["original", "structured", "summary", "magic"])
_VALID_LENGTH_DIRECTIONS = frozenset(["shorter", "longer"])
_VALID_EMOJI_DIRECTIONS = frozenset(["increase", "decrease", "few", "moderate"])
_VALID_DOWNLOAD_FORMATS = frozenset(["md", "txt", "pdf", "docx"])


def decode_callback_data(data: str) -> dict:
    """
    Decode callback data from compact format.

    Args:
        data: Encoded callback data string

    Returns:
        Dictionary with action, usage_id, and additional parameters

    Raises:
        ValueError: If data is empty, malformed, or contains invalid values
    """
    if not data or not isinstance(data, str):
        raise ValueError("Callback data must be a non-empty string")

    parts = data.split(":")
    if len(parts) < 2:
        raise ValueError(
            f"Callback data must have at least 2 parts (action:usage_id), got: {data!r}"
        )

    action = parts[0]
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Invalid action {action!r}, expected one of {sorted(_VALID_ACTIONS)}")

    try:
        usage_id = int(parts[1])
    except ValueError:
        raise ValueError(f"usage_id must be an integer, got: {parts[1]!r}")

    result: dict[str, Any] = {"action": action, "usage_id": usage_id}

    if len(parts) > 2:
        for param in parts[2].split(","):
            if "=" not in param:
                raise ValueError(f"Invalid parameter format {param!r}, expected key=value")
            key, value = param.split("=", 1)
            result[key] = value

    # Validate action-specific parameters
    if action == "mode" and "mode" in result:
        if result["mode"] not in _VALID_MODES:
            raise ValueError(
                f"Invalid mode {result['mode']!r}, expected one of {sorted(_VALID_MODES)}"
            )
    if action == "length" and "direction" in result:
        if result["direction"] not in _VALID_LENGTH_DIRECTIONS:
            raise ValueError(
                f"Invalid length direction {result['direction']!r}, "
                f"expected one of {sorted(_VALID_LENGTH_DIRECTIONS)}"
            )
    if action == "emoji" and "direction" in result:
        if result["direction"] not in _VALID_EMOJI_DIRECTIONS:
            raise ValueError(
                f"Invalid emoji direction {result['direction']!r}, "
                f"expected one of {sorted(_VALID_EMOJI_DIRECTIONS)}"
            )
    if action == "download_fmt" and "fmt" in result:
        if result["fmt"] not in _VALID_DOWNLOAD_FORMATS:
            raise ValueError(
                f"Invalid download format {result['fmt']!r}, "
                f"expected one of {sorted(_VALID_DOWNLOAD_FORMATS)}"
            )

    return result


def create_transcription_keyboard(
    state: TranscriptionState, has_segments: bool, settings: Settings
) -> InlineKeyboardMarkup | None:
    """
    Create inline keyboard for transcription message.

    Args:
        state: Current transcription state
        has_segments: Whether transcription has segments (for timestamps)
        settings: Application settings with feature flags

    Returns:
        InlineKeyboardMarkup or None if interactive mode is disabled
    """
    if not settings.interactive_mode_enabled:
        return None

    keyboard = []

    # Row 1: Original text (always shown if interactive mode enabled)
    label = "Исходный текст (вы здесь)" if state.active_mode == "original" else "Исходный текст"
    keyboard.append(
        [
            InlineKeyboardButton(
                label, callback_data=encode_callback_data("mode", state.usage_id, mode="original")
            )
        ]
    )

    # Row 2: Structured mode (Phase 2 + Phase 3 length variations)
    if settings.enable_structured_mode:
        if state.active_mode == "structured" and settings.enable_length_variations:
            # Phase 3: Dynamic 3-button layout [◀ Короче] [Indicator] [Длиннее ▶]
            row = []

            # Left button: "Короче" (hide at leftmost boundary)
            if state.length_level in ["short", "default", "long", "longer"]:
                row.append(
                    InlineKeyboardButton(
                        "◀ Короче",
                        callback_data=encode_callback_data(
                            "length", state.usage_id, direction="shorter"
                        ),
                    )
                )

            # Center button: Length indicator (non-interactive)
            level_indicators = {
                "shorter": "📝─",  # Minimum
                "short": "📝↓",  # Short
                "default": "📝",  # Default/middle
                "long": "📝↑",  # Long
                "longer": "📝+",  # Maximum
            }
            indicator = level_indicators.get(state.length_level, "📝")
            row.append(InlineKeyboardButton(indicator, callback_data="noop"))

            # Right button: "Длиннее" (hide at rightmost boundary)
            if state.length_level in ["shorter", "short", "default", "long"]:
                row.append(
                    InlineKeyboardButton(
                        "Длиннее ▶",
                        callback_data=encode_callback_data(
                            "length", state.usage_id, direction="longer"
                        ),
                    )
                )

            keyboard.append(row)
        else:
            # Single button (not in structured mode, or length variations disabled)
            label = (
                "📝 Структурировать (вы здесь)"
                if state.active_mode == "structured"
                else "📝 Структурировать"
            )
            keyboard.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=encode_callback_data(
                            "mode", state.usage_id, mode="structured"
                        ),
                    )
                ]
            )

    # Row 3: Summary mode (Phase 4)
    if settings.enable_summary_mode:
        if state.active_mode == "summary" and settings.enable_length_variations:
            # Phase 4: Dynamic 3-button layout for summary mode
            row = []

            # Left button: "Короче" (hide at leftmost boundary)
            if state.length_level in ["short", "default", "long", "longer"]:
                row.append(
                    InlineKeyboardButton(
                        "◀ Короче",
                        callback_data=encode_callback_data(
                            "length", state.usage_id, direction="shorter"
                        ),
                    )
                )

            # Center button: Length indicator (non-interactive)
            level_indicators = {
                "shorter": "💡─",  # Minimum
                "short": "💡↓",  # Short
                "default": "💡",  # Default/middle
                "long": "💡↑",  # Long
                "longer": "💡+",  # Maximum
            }
            indicator = level_indicators.get(state.length_level, "💡")
            row.append(InlineKeyboardButton(indicator, callback_data="noop"))

            # Right button: "Длиннее" (hide at rightmost boundary)
            if state.length_level in ["shorter", "short", "default", "long"]:
                row.append(
                    InlineKeyboardButton(
                        "Длиннее ▶",
                        callback_data=encode_callback_data(
                            "length", state.usage_id, direction="longer"
                        ),
                    )
                )

            keyboard.append(row)
        else:
            # Single button (not in summary mode, or length variations disabled)
            label = (
                "📌 О чем текст? (вы здесь)"
                if state.active_mode == "summary"
                else "📌 О чем текст?"
            )
            keyboard.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=encode_callback_data("mode", state.usage_id, mode="summary"),
                    )
                ]
            )

    # Row 4: Magic mode (Phase 9) - publication-ready text
    if settings.enable_magic_mode:
        label = (
            "🪄 Сделать красиво (вы здесь)"
            if state.active_mode == "magic"
            else "🪄 Сделать красиво"
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=encode_callback_data("mode", state.usage_id, mode="magic"),
                )
            ]
        )

    # Row 5: Emoji option (Phase 5)
    if settings.enable_emoji_option:
        if state.emoji_level > 0:
            # Emoji mode active: show controls
            if state.active_mode == "original":
                # Original mode: 3 buttons [Меньше/Убрать] [Indicator] [Больше]
                row = []

                # Left button: Decrease emoji level
                label = "Убрать" if state.emoji_level == 1 else "Меньше"
                row.append(
                    InlineKeyboardButton(
                        label,
                        callback_data=encode_callback_data(
                            "emoji", state.usage_id, direction="decrease"
                        ),
                    )
                )

                # Center button: Emoji indicator (non-interactive)
                # 4 levels: 0 (none), 1 (few), 2 (moderate), 3 (many)
                emoji_indicators = {
                    1: "😊",  # Few (default)
                    2: "😊😊",  # Moderate
                    3: "😊😊😊",  # Many
                }
                indicator = emoji_indicators.get(state.emoji_level, "😊")
                row.append(InlineKeyboardButton(indicator, callback_data="noop"))

                # Right button: Increase emoji level (only if not at max)
                if state.emoji_level < 3:
                    row.append(
                        InlineKeyboardButton(
                            "Больше",
                            callback_data=encode_callback_data(
                                "emoji", state.usage_id, direction="increase"
                            ),
                        )
                    )

                keyboard.append(row)
            else:
                # Structured/Summary modes: single toggle button to remove emojis
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "😊 Убрать смайлы",
                            callback_data=encode_callback_data(
                                "emoji", state.usage_id, direction="decrease"
                            ),
                        )
                    ]
                )
        else:
            # No emojis: single button to add emojis (defaults to level 1 - few)
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "😊 Смайлы",
                        callback_data=encode_callback_data(
                            "emoji", state.usage_id, direction="few"
                        ),
                    )
                ]
            )

    # Row 6: Timestamps option (Phase 6) - only if has segments (>5 min audio)
    if settings.enable_timestamps_option and has_segments:
        label = "Убрать таймкоды" if state.timestamps_enabled else "🕐 Таймкоды"
        keyboard.append(
            [
                InlineKeyboardButton(
                    label, callback_data=encode_callback_data("timestamps", state.usage_id)
                )
            ]
        )

    # Row 7: Retranscribe (Phase 8) - only if audio file is saved
    if settings.enable_retranscribe:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "⚡ Есть ошибки? Могу лучше!",
                    callback_data=encode_callback_data("retranscribe_menu", state.usage_id),
                )
            ]
        )

    return InlineKeyboardMarkup(keyboard) if keyboard else None
