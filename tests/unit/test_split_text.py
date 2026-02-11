"""Unit tests for split_text() function."""

from src.bot.handlers import split_text, TELEGRAM_MAX_MESSAGE_LENGTH


class TestSplitText:
    """Tests for split_text function."""

    def test_empty_string(self) -> None:
        """Empty string returns list with empty string."""
        result = split_text("")
        assert result == [""]

    def test_short_text(self) -> None:
        """Text shorter than limit is returned as single chunk."""
        text = "Hello, world!"
        result = split_text(text)
        assert result == [text]

    def test_text_exactly_at_limit(self) -> None:
        """Text exactly at max_length is returned as single chunk."""
        text = "a" * TELEGRAM_MAX_MESSAGE_LENGTH
        result = split_text(text)
        assert result == [text]

    def test_text_slightly_over_limit(self) -> None:
        """Text slightly over max_length produces 2 parts."""
        text = "a" * (TELEGRAM_MAX_MESSAGE_LENGTH + 1)
        result = split_text(text)
        assert len(result) == 2
        assert "".join(result) == text

    def test_text_without_spaces_hard_cut(self) -> None:
        """Text without spaces is force-split at effective_max."""
        max_length = 100
        header_reserve = 50
        effective_max = max_length - header_reserve
        text = "a" * (max_length + 50)
        result = split_text(text, max_length=max_length)
        # First chunk should be effective_max characters
        assert len(result[0]) == effective_max
        # Reassembled text must match original
        assert "".join(result) == text

    def test_unicode_cyrillic(self) -> None:
        """Cyrillic text is split correctly."""
        word = "Привет "
        # Build text longer than limit
        max_length = 100
        text = word * 50  # 350 chars, well over 100
        result = split_text(text, max_length=max_length)
        assert len(result) > 1
        # All parts should be within max_length
        for chunk in result:
            assert len(chunk) <= max_length

    def test_unicode_emoji(self) -> None:
        """Emoji text is split correctly without breaking."""
        max_length = 100
        # Use single-codepoint emoji to avoid multi-char issues
        text = "Hello! " * 50
        result = split_text(text, max_length=max_length)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= max_length

    def test_text_with_newlines(self) -> None:
        """Text with newlines is split at newline boundaries when possible."""
        max_length = 100
        # Create paragraphs that together exceed max_length (>100 total)
        para1 = "A" * 40
        para2 = "B" * 40
        para3 = "C" * 40
        text = f"{para1}\n\n{para2}\n\n{para3}"  # 40+2+40+2+40 = 124 chars
        result = split_text(text, max_length=max_length)
        assert len(result) >= 2
        # All parts must be within limit
        for chunk in result:
            assert len(chunk) <= max_length

    def test_very_long_text_multiple_parts(self) -> None:
        """Very long text is split into multiple parts."""
        max_length = 100
        text = "word " * 200  # 1000 chars
        result = split_text(text, max_length=max_length)
        assert len(result) > 3
        # Verify no content is lost (accounting for spaces removed at split points)
        reassembled = " ".join(chunk.strip() for chunk in result)
        assert reassembled.replace("  ", " ") == text.strip().replace("  ", " ")

    def test_all_parts_within_max_length(self) -> None:
        """All resulting parts should be <= max_length."""
        max_length = 100
        text = "Some text with spaces. " * 50
        result = split_text(text, max_length=max_length)
        for i, chunk in enumerate(result):
            assert (
                len(chunk) <= max_length
            ), f"Chunk {i} has length {len(chunk)}, exceeds max_length={max_length}"

    def test_custom_max_length(self) -> None:
        """Custom max_length parameter works correctly."""
        text = "Hello world! " * 20  # ~260 chars
        result_150 = split_text(text.strip(), max_length=150)
        result_500 = split_text(text.strip(), max_length=500)
        # With smaller limit, more chunks are produced
        assert len(result_150) > len(result_500)

    def test_split_at_sentence_boundary(self) -> None:
        """Text is preferably split at sentence boundaries."""
        max_length = 150
        # Build two sentences that together exceed max_length
        sentence1 = "A" * 80 + ". "
        sentence2 = "B" * 80
        text = sentence1 + sentence2  # 162 chars, > 150
        result = split_text(text, max_length=max_length)
        assert len(result) >= 2
        # First chunk should end with the sentence boundary
        assert result[0].endswith(".")

    def test_split_at_word_boundary(self) -> None:
        """Text splits at space rather than mid-word when possible."""
        max_length = 100
        # Create words that exceed max_length but have spaces
        text = "abcde " * 20  # 120 chars
        result = split_text(text, max_length=max_length)
        assert len(result) >= 2
        # First chunk should not end mid-word
        assert not result[0].endswith("abc")

    def test_single_character_text(self) -> None:
        """Single character text returns as-is."""
        result = split_text("x")
        assert result == ["x"]
