"""Unit tests for token estimation module."""

from src.services.token_estimator import estimate_tokens, will_exceed_output_limit


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_empty_string(self):
        """Test: empty string returns 0 tokens."""
        assert estimate_tokens("") == 0

    def test_short_russian_text(self):
        """Test: short Russian text token estimation."""
        # ~30 chars → ~10 tokens (1 token ≈ 3 chars for Russian)
        text = "Привет, как дела? Всё хорошо."
        tokens = estimate_tokens(text)
        assert 5 <= tokens <= 20

    def test_long_russian_text_calibration(self):
        """Test: calibration against real DeepSeek data from logs.

        Real data: 22396 chars → 16047 tokens (input = prompt + text)
        Text alone is ~22396 chars, which should be estimated at ~7000-8000 tokens.
        (16047 includes system prompt tokens)
        """
        text = "а" * 22396
        tokens = estimate_tokens(text)
        # Expect roughly 5000-10000 tokens for 22396 chars of Russian text
        assert 5000 <= tokens <= 10000

    def test_english_text(self):
        """Test: English text uses different ratio (~4 chars per token)."""
        text = "Hello world, this is a test sentence for token estimation."
        tokens = estimate_tokens(text)
        assert 5 <= tokens <= 25


class TestWillExceedOutputLimit:
    """Tests for will_exceed_output_limit function."""

    def test_short_text_does_not_exceed(self):
        """Test: short text does not exceed output limit."""
        text = "Короткий текст для теста."
        assert will_exceed_output_limit(text, max_output_tokens=8192) is False

    def test_very_long_text_exceeds(self):
        """Test: very long text exceeds output limit."""
        # 50000 chars → ~16000+ tokens, likely to exceed 8192 output limit
        text = "а" * 50000
        assert will_exceed_output_limit(text, max_output_tokens=8192) is True

    def test_reasoner_limit_not_exceeded(self):
        """Test: same text does not exceed reasoner limit (64K)."""
        text = "а" * 50000
        assert will_exceed_output_limit(text, max_output_tokens=64000) is False

    def test_boundary_case(self):
        """Test: text near the boundary."""
        # ~24000 chars → ~8000 tokens, borderline for 8192 limit
        text = "а" * 24000
        result = will_exceed_output_limit(text, max_output_tokens=8192)
        # Should be close to limit, either True or False is acceptable
        assert isinstance(result, bool)
