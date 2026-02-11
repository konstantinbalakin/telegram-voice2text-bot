"""Tests for src/bot/keyboards.py — encode, decode, and create_transcription_keyboard."""

from unittest.mock import MagicMock

import pytest

from src.bot.keyboards import (
    _VALID_ACTIONS,
    create_transcription_keyboard,
    decode_callback_data,
    encode_callback_data,
)


# ---------------------------------------------------------------------------
# encode_callback_data
# ---------------------------------------------------------------------------


class TestEncodeCallbackData:
    def test_basic_encode(self) -> None:
        result = encode_callback_data("mode", 123)
        assert result == "mode:123"

    def test_encode_with_params(self) -> None:
        result = encode_callback_data("mode", 123, mode="structured")
        assert result == "mode:123:mode=structured"

    def test_encode_with_multiple_params(self) -> None:
        result = encode_callback_data("length", 5, direction="shorter", extra="val")
        assert "length:5:" in result
        assert "direction=shorter" in result
        assert "extra=val" in result

    def test_encode_exactly_64_bytes(self) -> None:
        # "mode:123:" = 9 bytes, need 55 more for params
        long_val = "x" * 50
        result = encode_callback_data("mode", 123, k=long_val)
        assert len(result.encode("utf-8")) <= 64

    def test_encode_exceeds_64_bytes_raises(self) -> None:
        long_val = "x" * 100
        with pytest.raises(ValueError, match="too long"):
            encode_callback_data("mode", 123, k=long_val)


# ---------------------------------------------------------------------------
# decode_callback_data
# ---------------------------------------------------------------------------


class TestDecodeCallbackData:
    def test_simple_decode(self) -> None:
        result = decode_callback_data("mode:123")
        assert result == {"action": "mode", "usage_id": 123}

    def test_decode_with_params(self) -> None:
        result = decode_callback_data("mode:123:mode=structured")
        assert result == {"action": "mode", "usage_id": 123, "mode": "structured"}

    def test_roundtrip(self) -> None:
        encoded = encode_callback_data("emoji", 42, direction="increase")
        decoded = decode_callback_data(encoded)
        assert decoded["action"] == "emoji"
        assert decoded["usage_id"] == 42
        assert decoded["direction"] == "increase"

    def test_roundtrip_no_params(self) -> None:
        encoded = encode_callback_data("timestamps", 7)
        decoded = decode_callback_data(encoded)
        assert decoded == {"action": "timestamps", "usage_id": 7}

    def test_all_valid_actions_accepted(self) -> None:
        for action in _VALID_ACTIONS:
            result = decode_callback_data(f"{action}:1")
            assert result["action"] == action

    # --- Validation error cases ---

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            decode_callback_data("")

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            decode_callback_data(None)  # type: ignore[arg-type]

    def test_missing_usage_id_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 parts"):
            decode_callback_data("mode")

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid action"):
            decode_callback_data("invalid_action:123")

    def test_non_integer_usage_id_raises(self) -> None:
        with pytest.raises(ValueError, match="usage_id must be an integer"):
            decode_callback_data("mode:abc")

    def test_invalid_mode_value_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid mode"):
            decode_callback_data("mode:1:mode=nonexistent")

    def test_invalid_length_direction_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid length direction"):
            decode_callback_data("length:1:direction=sideways")

    def test_invalid_emoji_direction_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid emoji direction"):
            decode_callback_data("emoji:1:direction=sideways")

    def test_valid_mode_values(self) -> None:
        for mode in ("original", "structured", "summary", "magic"):
            result = decode_callback_data(f"mode:1:mode={mode}")
            assert result["mode"] == mode

    def test_valid_length_directions(self) -> None:
        for direction in ("shorter", "longer"):
            result = decode_callback_data(f"length:1:direction={direction}")
            assert result["direction"] == direction

    def test_valid_emoji_directions(self) -> None:
        for direction in ("increase", "decrease", "few", "moderate"):
            result = decode_callback_data(f"emoji:1:direction={direction}")
            assert result["direction"] == direction

    def test_malformed_param_no_equals_raises(self) -> None:
        with pytest.raises(ValueError, match="expected key=value"):
            decode_callback_data("mode:1:badparam")

    def test_noop_action(self) -> None:
        result = decode_callback_data("noop:0")
        assert result["action"] == "noop"


# ---------------------------------------------------------------------------
# create_transcription_keyboard
# ---------------------------------------------------------------------------


def _make_state(**overrides: object) -> MagicMock:
    """Create a mock TranscriptionState with sensible defaults."""
    defaults = {
        "usage_id": 1,
        "active_mode": "original",
        "length_level": "default",
        "emoji_level": 0,
        "timestamps_enabled": False,
    }
    defaults.update(overrides)
    state = MagicMock()
    for k, v in defaults.items():
        setattr(state, k, v)
    return state


def _make_settings(**overrides: object) -> MagicMock:
    """Create a mock Settings with sensible defaults."""
    defaults = {
        "interactive_mode_enabled": True,
        "enable_structured_mode": True,
        "enable_summary_mode": True,
        "enable_magic_mode": True,
        "enable_emoji_option": False,
        "enable_timestamps_option": False,
        "enable_length_variations": False,
        "enable_retranscribe": False,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


class TestCreateTranscriptionKeyboard:
    def test_interactive_disabled_returns_none(self) -> None:
        state = _make_state()
        settings = _make_settings(interactive_mode_enabled=False)
        assert create_transcription_keyboard(state, False, settings) is None

    def test_basic_keyboard_original_mode(self) -> None:
        state = _make_state(active_mode="original")
        settings = _make_settings()
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        # Should have original + structured + summary + magic = 4 rows
        assert len(kb.inline_keyboard) == 4
        # First row label for active mode
        assert "(вы здесь)" in kb.inline_keyboard[0][0].text

    def test_structured_mode_not_shown_when_disabled(self) -> None:
        state = _make_state()
        settings = _make_settings(enable_structured_mode=False)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        # Should have original + summary + magic = 3 rows
        assert len(kb.inline_keyboard) == 3

    def test_summary_mode_not_shown_when_disabled(self) -> None:
        state = _make_state()
        settings = _make_settings(enable_summary_mode=False)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        # Should have original + structured + magic = 3 rows
        assert len(kb.inline_keyboard) == 3

    def test_magic_mode_not_shown_when_disabled(self) -> None:
        state = _make_state()
        settings = _make_settings(enable_magic_mode=False)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        # Should have original + structured + summary = 3 rows
        assert len(kb.inline_keyboard) == 3

    def test_structured_active_with_length_variations(self) -> None:
        state = _make_state(active_mode="structured", length_level="default")
        settings = _make_settings(enable_length_variations=True)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        # Row 2 should have 3 buttons: shorter, indicator, longer
        row2 = kb.inline_keyboard[1]
        assert len(row2) == 3
        assert row2[0].text == "◀ Короче"
        assert row2[2].text == "Длиннее ▶"

    def test_structured_at_min_length_hides_shorter_button(self) -> None:
        state = _make_state(active_mode="structured", length_level="shorter")
        settings = _make_settings(enable_length_variations=True)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        row2 = kb.inline_keyboard[1]
        # At "shorter" boundary: only indicator + "Длиннее"
        assert len(row2) == 2

    def test_structured_at_max_length_hides_longer_button(self) -> None:
        state = _make_state(active_mode="structured", length_level="longer")
        settings = _make_settings(enable_length_variations=True)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        row2 = kb.inline_keyboard[1]
        # At "longer" boundary: "Короче" + indicator
        assert len(row2) == 2

    def test_emoji_button_shown_when_enabled(self) -> None:
        state = _make_state(emoji_level=0)
        settings = _make_settings(enable_emoji_option=True)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        # Last row should be emoji button
        last_row = kb.inline_keyboard[-1]
        assert "Смайлы" in last_row[0].text

    def test_timestamps_button_shown_when_has_segments(self) -> None:
        state = _make_state()
        settings = _make_settings(enable_timestamps_option=True)
        kb = create_transcription_keyboard(state, has_segments=True, settings=settings)
        assert kb is not None
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Таймкоды" in t for t in texts)

    def test_timestamps_button_hidden_without_segments(self) -> None:
        state = _make_state()
        settings = _make_settings(enable_timestamps_option=True)
        kb = create_transcription_keyboard(state, has_segments=False, settings=settings)
        assert kb is not None
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert not any("Таймкоды" in t for t in texts)

    def test_retranscribe_button_shown_when_enabled(self) -> None:
        state = _make_state()
        settings = _make_settings(enable_retranscribe=True)
        kb = create_transcription_keyboard(state, False, settings)
        assert kb is not None
        last_row = kb.inline_keyboard[-1]
        assert "Могу лучше" in last_row[0].text
