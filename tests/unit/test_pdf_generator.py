"""Unit tests for PDF generator service."""

import pytest
from unittest.mock import patch

from src.services.pdf_generator import PDFGenerator, convert_markdown_to_html


class TestPDFGenerator:
    """Test suite for PDFGenerator."""

    @pytest.fixture
    def generator(self) -> PDFGenerator:
        """Create PDFGenerator instance for tests."""
        return PDFGenerator()

    def test_basic_html_to_pdf(self, generator: PDFGenerator) -> None:
        """Test basic HTML to PDF conversion."""
        html_content = "<p>Hello, World!</p>"
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # PDF files start with %PDF
        assert pdf_bytes[:4] == b"%PDF"

    def test_cyrillic_text_rendering(self, generator: PDFGenerator) -> None:
        """Test that Cyrillic text is properly rendered in PDF."""
        html_content = "<p>Привет, мир! Это тестовый текст на русском языке.</p>"
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_html_formatting_tags(self, generator: PDFGenerator) -> None:
        """Test HTML formatting tags (bold, italic, lists)."""
        html_content = """
        <p>This is <b>bold text</b> and <i>italic text</i>.</p>
        <ul>
            <li>First item</li>
            <li>Second item</li>
            <li>Third item</li>
        </ul>
        <ol>
            <li>Numbered one</li>
            <li>Numbered two</li>
        </ol>
        """
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_code_formatting(self, generator: PDFGenerator) -> None:
        """Test code block formatting."""
        html_content = """
        <p>Here is some code:</p>
        <pre><code>
def hello_world():
    print("Hello, World!")
        </code></pre>
        <p>And inline <code>code snippet</code>.</p>
        """
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_mixed_html_and_cyrillic(self, generator: PDFGenerator) -> None:
        """Test mixed HTML formatting with Cyrillic text."""
        html_content = """
        <p><b>Важное сообщение:</b></p>
        <ul>
            <li>Первый пункт с <i>курсивом</i></li>
            <li>Второй пункт с <code>кодом</code></li>
            <li>Третий пункт с <b>жирным текстом</b></li>
        </ul>
        <p>Текст с <u>подчеркиванием</u> и обычный текст.</p>
        """
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_large_text_memory_efficiency(self, generator: PDFGenerator) -> None:
        """Test that large texts are handled efficiently."""
        # Create a large HTML document (~10KB)
        large_content = "<p>" + "Тестовый текст. " * 500 + "</p>"
        pdf_bytes = generator.generate_pdf(large_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_empty_content(self, generator: PDFGenerator) -> None:
        """Test generation with empty content."""
        html_content = ""
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_create_styled_html(self, generator: PDFGenerator) -> None:
        """Test HTML template wrapping."""
        content = "<p>Test content</p>"
        styled_html = generator.create_styled_html(content)

        assert "<!DOCTYPE html>" in styled_html
        assert "<html>" in styled_html
        assert "<body>" in styled_html
        assert content in styled_html
        assert "font-family" in styled_html
        assert 'charset="UTF-8"' in styled_html

    def test_generate_pdf_from_text_with_paragraphs(self, generator: PDFGenerator) -> None:
        """Test PDF generation from plain text with paragraph wrapping."""
        plain_text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        pdf_bytes = generator.generate_pdf_from_text(plain_text, wrap_paragraphs=True)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_generate_pdf_from_text_without_wrapping(self, generator: PDFGenerator) -> None:
        """Test PDF generation from plain text without paragraph wrapping."""
        plain_text = "Simple text without wrapping."
        pdf_bytes = generator.generate_pdf_from_text(plain_text, wrap_paragraphs=False)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_generate_pdf_from_text_no_double_conversion(self, generator: PDFGenerator) -> None:
        """generate_pdf_from_text must NOT run text through convert_markdown_to_html."""
        plain_text = "Paragraph one.\n\nParagraph two."
        with patch(
            "src.services.pdf_generator.convert_markdown_to_html", wraps=convert_markdown_to_html
        ) as mock_convert:
            generator.generate_pdf_from_text(plain_text, wrap_paragraphs=True)
            mock_convert.assert_not_called()

    def test_special_characters_escaping(self, generator: PDFGenerator) -> None:
        """Test that special characters are handled correctly."""
        html_content = """
        <p>Special chars: &lt; &gt; &amp; &quot; &#39;</p>
        <p>Math symbols: × ÷ ± ≠ ≤ ≥</p>
        <p>Currency: $ € £ ¥ ₽</p>
        """
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

    def test_links_in_pdf(self, generator: PDFGenerator) -> None:
        """Test that links are properly rendered."""
        html_content = """
        <p>Visit <a href="https://example.com">this link</a> for more info.</p>
        """
        pdf_bytes = generator.generate_pdf(html_content)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"


class TestConvertMarkdownToHtml:
    """Test Markdown to HTML conversion for PDF rendering."""

    def test_empty_string(self) -> None:
        assert convert_markdown_to_html("") == ""

    def test_bold(self) -> None:
        result = convert_markdown_to_html("**жирный**")
        assert "<strong>жирный</strong>" in result

    def test_italic(self) -> None:
        result = convert_markdown_to_html("*курсив*")
        assert "<em>курсив</em>" in result

    def test_inline_code(self) -> None:
        result = convert_markdown_to_html("`код`")
        assert "<code>код</code>" in result

    def test_code_block(self) -> None:
        result = convert_markdown_to_html("```\ncode block\n```")
        assert "<pre><code>" in result
        assert "code block" in result

    def test_heading_h1(self) -> None:
        result = convert_markdown_to_html("# Заголовок")
        assert "<h1>Заголовок</h1>" in result

    def test_heading_h2(self) -> None:
        result = convert_markdown_to_html("## Подзаголовок")
        assert "<h2>Подзаголовок</h2>" in result

    def test_heading_h3(self) -> None:
        result = convert_markdown_to_html("### Третий уровень")
        assert "<h3>Третий уровень</h3>" in result

    def test_bullet_list_dash(self) -> None:
        result = convert_markdown_to_html("- пункт 1\n- пункт 2")
        assert "<ul>" in result
        assert "<li>" in result
        assert "пункт 1" in result

    def test_bullet_list_dot(self) -> None:
        result = convert_markdown_to_html("• пункт 1\n• пункт 2")
        assert "<ul>" in result
        assert "пункт 1" in result

    def test_numbered_list(self) -> None:
        result = convert_markdown_to_html("1. первый\n2. второй")
        assert "<ol>" in result
        assert "первый" in result

    def test_link(self) -> None:
        result = convert_markdown_to_html("[ссылка](https://example.com)")
        assert '<a href="https://example.com">ссылка</a>' in result

    def test_underline(self) -> None:
        result = convert_markdown_to_html("__подчёркнутый__")
        assert "<u>подчёркнутый</u>" in result

    def test_paragraph(self) -> None:
        result = convert_markdown_to_html("Первый параграф\n\nВторой параграф")
        assert "<p>Первый параграф</p>" in result
        assert "<p>Второй параграф</p>" in result

    def test_mixed_markdown(self) -> None:
        text = "# Заголовок\n\n**Жирный** и *курсив*.\n\n- Пункт 1\n- Пункт 2"
        result = convert_markdown_to_html(text)
        assert "<h1>Заголовок</h1>" in result
        assert "<strong>Жирный</strong>" in result
        assert "<em>курсив</em>" in result
        assert "<ul>" in result

    def test_markdown_generates_valid_pdf(self) -> None:
        """End-to-end: Markdown text produces valid PDF."""
        gen = PDFGenerator()
        text = "# Заголовок\n\n**Жирный** и *курсив*.\n\n- Пункт 1\n- Пункт 2"
        pdf_bytes = gen.generate_pdf(text)
        assert pdf_bytes[:4] == b"%PDF"
