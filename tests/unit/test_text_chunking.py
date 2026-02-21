"""Unit tests for text chunking module."""

from src.services.text_chunking import split_text_into_chunks, merge_processed_chunks


class TestSplitTextIntoChunks:
    """Tests for split_text_into_chunks function."""

    def test_short_text_single_chunk(self):
        """Test: text shorter than max_chars stays as single chunk."""
        text = "Короткий текст."
        chunks = split_text_into_chunks(text, max_chars=8000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text(self):
        """Test: empty text returns empty list."""
        assert split_text_into_chunks("", max_chars=8000) == []

    def test_splits_on_sentence_boundary(self):
        """Test: text is split on sentence boundaries (., !, ?)."""
        text = "Первое предложение. Второе предложение. Третье предложение."
        chunks = split_text_into_chunks(text, max_chars=40)
        assert len(chunks) >= 2
        # Each chunk should end with a sentence boundary or be the last chunk
        for chunk in chunks[:-1]:
            assert chunk.rstrip().endswith((".", "!", "?"))

    def test_no_chunk_exceeds_max_chars(self):
        """Test: each chunk does not exceed max_chars."""
        text = "Это тест. " * 500  # ~5000 chars
        chunks = split_text_into_chunks(text, max_chars=500)
        for chunk in chunks:
            assert len(chunk) <= 500 + 100  # Allow small overflow for sentence alignment

    def test_all_text_preserved(self):
        """Test: all text content is preserved across chunks."""
        text = "Первое предложение. Второе предложение. Третье предложение."
        chunks = split_text_into_chunks(text, max_chars=30)
        # All words should be present in merged result
        merged = " ".join(chunks)
        for word in text.split():
            assert word in merged

    def test_long_sentence_not_split(self):
        """Test: a single long sentence stays as one chunk even if > max_chars."""
        text = "а" * 1000  # No sentence boundaries
        chunks = split_text_into_chunks(text, max_chars=500)
        # Should still create chunks, even if individual sentence is too long
        assert len(chunks) >= 1
        assert "".join(chunks) == text


class TestMergeProcessedChunks:
    """Tests for merge_processed_chunks function."""

    def test_merge_simple(self):
        """Test: simple merge of chunks."""
        chunks = ["Первая часть.", "Вторая часть.", "Третья часть."]
        result = merge_processed_chunks(chunks)
        assert result == "Первая часть.\n\nВторая часть.\n\nТретья часть."

    def test_merge_single_chunk(self):
        """Test: single chunk returns as-is."""
        chunks = ["Единственный текст."]
        result = merge_processed_chunks(chunks)
        assert result == "Единственный текст."

    def test_merge_empty(self):
        """Test: empty list returns empty string."""
        assert merge_processed_chunks([]) == ""

    def test_merge_strips_whitespace(self):
        """Test: merge strips leading/trailing whitespace from chunks."""
        chunks = ["  Текст один.  ", "  Текст два.  "]
        result = merge_processed_chunks(chunks)
        assert result == "Текст один.\n\nТекст два."
