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


def decode_callback_data(data: str) -> dict:
    """
    Decode callback data from compact format.

    Args:
        data: Encoded callback data string

    Returns:
        Dictionary with action, usage_id, and additional parameters
    """
    parts = data.split(":")
    result = {"action": parts[0], "usage_id": int(parts[1])}

    if len(parts) > 2:
        for param in parts[2].split(","):
            key, value = param.split("=")
            result[key] = value

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

    # Note: Rows 3-6 will be added in future phases
    # Row 3: Summary mode (Phase 4)
    # Row 4: Emoji option (Phase 5)
    # Row 5: Timestamps option (Phase 6)
    # Row 6: Retranscribe (Phase 8)

    return InlineKeyboardMarkup(keyboard) if keyboard else None
