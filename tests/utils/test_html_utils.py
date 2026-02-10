"""Tests for HTML utilities."""

from src.utils.html_utils import sanitize_html, escape_html


class TestSanitizeHtml:
    """Tests for sanitize_html function."""

    def test_keeps_supported_tags(self):
        """Should keep Telegram-supported tags."""
        html = "<b>Bold</b> <i>italic</i> <code>code</code> <u>underline</u>"
        result = sanitize_html(html)
        assert result == html

    def test_strips_paragraph_tags(self):
        """Should strip <p> tags but keep content."""
        html = "<p>Hello world</p>"
        result = sanitize_html(html)
        assert result == "Hello world"

    def test_strips_div_tags(self):
        """Should strip <div> tags but keep content."""
        html = "<div>Content here</div>"
        result = sanitize_html(html)
        assert result == "Content here"

    def test_strips_list_tags(self):
        """Should strip list tags but keep content."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = sanitize_html(html)
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<ul>" not in result
        assert "<li>" not in result

    def test_strips_header_tags(self):
        """Should strip header tags but keep content."""
        html = "<h1>Title</h1><h2>Subtitle</h2>"
        result = sanitize_html(html)
        assert "Title" in result
        assert "Subtitle" in result
        assert "<h1>" not in result
        assert "<h2>" not in result

    def test_strips_br_tags(self):
        """Should strip <br> tags."""
        html = "Line 1<br>Line 2<br/>Line 3"
        result = sanitize_html(html)
        assert "<br" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_mixed_supported_and_unsupported(self):
        """Should keep supported tags and strip unsupported ones."""
        html = "<p>Text with <b>bold</b> and <i>italic</i></p>"
        result = sanitize_html(html)
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<p>" not in result

    def test_nested_tags(self):
        """Should handle nested tags correctly."""
        html = "<div><p>Outer <b>bold <i>and italic</i></b> text</p></div>"
        result = sanitize_html(html)
        assert "<b>bold <i>and italic</i></b>" in result
        assert "<div>" not in result
        assert "<p>" not in result

    def test_empty_string(self):
        """Should handle empty string."""
        assert sanitize_html("") == ""

    def test_none_input(self):
        """Should handle None input."""
        assert sanitize_html(None) is None

    def test_no_tags(self):
        """Should return plain text unchanged."""
        text = "Just plain text"
        assert sanitize_html(text) == text

    def test_cleans_multiple_newlines(self):
        """Should reduce multiple consecutive newlines to max 2."""
        html = "Line 1\n\n\n\n\nLine 2"
        result = sanitize_html(html)
        assert result == "Line 1\n\nLine 2"

    def test_cleans_multiple_spaces(self):
        """Should reduce multiple spaces to single space."""
        html = "Text  with    many     spaces"
        result = sanitize_html(html)
        assert result == "Text with many spaces"

    def test_trims_whitespace(self):
        """Should trim leading and trailing whitespace."""
        html = "  \n  Text  \n  "
        result = sanitize_html(html)
        assert result == "Text"

    def test_real_world_example(self):
        """Test with real-world problematic HTML."""
        html = """<p>Привет! Это тест.</p>

<p>Вот список:</p>
<ul>
<li>Пункт 1</li>
<li>Пункт 2</li>
</ul>

<p>И <b>важный</b> текст.</p>"""
        result = sanitize_html(html)

        # Should keep bold tag
        assert "<b>важный</b>" in result

        # Should remove all <p>, <ul>, <li> tags
        assert "<p>" not in result
        assert "<ul>" not in result
        assert "<li>" not in result

        # Should keep content
        assert "Привет! Это тест." in result
        assert "Пункт 1" in result
        assert "Пункт 2" in result


class TestEscapeHtml:
    """Tests for escape_html function."""

    def test_escapes_ampersand(self):
        """Should escape & character."""
        assert escape_html("A & B") == "A &amp; B"

    def test_escapes_less_than(self):
        """Should escape < character."""
        assert escape_html("A < B") == "A &lt; B"

    def test_escapes_greater_than(self):
        """Should escape > character."""
        assert escape_html("A > B") == "A &gt; B"

    def test_escapes_quotes(self):
        """Should escape quote characters."""
        assert escape_html('Say "hello"') == "Say &quot;hello&quot;"
        assert escape_html("It's good") == "It&#39;s good"

    def test_escapes_all_special_chars(self):
        """Should escape all special HTML characters."""
        text = """<script>alert("XSS & bad stuff")</script>"""
        result = escape_html(text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&quot;" in result
        assert "&amp;" in result

    def test_empty_string(self):
        """Should handle empty string."""
        assert escape_html("") == ""

    def test_none_input(self):
        """Should handle None input."""
        assert escape_html(None) is None

    def test_no_special_chars(self):
        """Should return text unchanged if no special chars."""
        text = "Just normal text"
        assert escape_html(text) == text
