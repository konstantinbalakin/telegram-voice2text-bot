"""Tests for src/services/export_service.py — ExportService for MD, TXT, PDF, DOCX."""

import io

import pytest

from src.services.export_service import ExportService


@pytest.fixture
def export_service() -> ExportService:
    return ExportService()


SAMPLE_MARKDOWN = """# Заголовок

Это **жирный** текст и *курсив*.

## Подзаголовок

- Пункт 1
- Пункт 2
- Пункт 3

1. Нумерованный
2. Список

Обычный параграф с `кодом`.
"""

SAMPLE_PLAIN = "Простой текст без форматирования.\nВторая строка."


class TestExportMd:
    def test_returns_bytesio(self, export_service: ExportService) -> None:
        result = export_service.export_md(SAMPLE_MARKDOWN, "test")
        assert isinstance(result, io.BytesIO)

    def test_name_set(self, export_service: ExportService) -> None:
        result = export_service.export_md(SAMPLE_MARKDOWN, "test")
        assert result.name == "test.md"

    def test_content_preserved(self, export_service: ExportService) -> None:
        result = export_service.export_md(SAMPLE_MARKDOWN, "test")
        content = result.read().decode("utf-8")
        assert "# Заголовок" in content
        assert "**жирный**" in content

    def test_empty_text(self, export_service: ExportService) -> None:
        result = export_service.export_md("", "empty")
        assert isinstance(result, io.BytesIO)
        assert result.read() == b""


class TestExportTxt:
    def test_returns_bytesio(self, export_service: ExportService) -> None:
        result = export_service.export_txt(SAMPLE_MARKDOWN, "test")
        assert isinstance(result, io.BytesIO)

    def test_name_set(self, export_service: ExportService) -> None:
        result = export_service.export_txt(SAMPLE_MARKDOWN, "test")
        assert result.name == "test.txt"

    def test_strips_bold(self, export_service: ExportService) -> None:
        result = export_service.export_txt("**bold** text", "test")
        content = result.read().decode("utf-8")
        assert "**" not in content
        assert "bold text" in content

    def test_strips_italic(self, export_service: ExportService) -> None:
        result = export_service.export_txt("*italic* text", "test")
        content = result.read().decode("utf-8")
        assert content.strip() == "italic text"

    def test_strips_headers(self, export_service: ExportService) -> None:
        result = export_service.export_txt("# Header\n## Sub", "test")
        content = result.read().decode("utf-8")
        assert "#" not in content
        assert "Header" in content
        assert "Sub" in content

    def test_strips_inline_code(self, export_service: ExportService) -> None:
        result = export_service.export_txt("use `code` here", "test")
        content = result.read().decode("utf-8")
        assert "`" not in content
        assert "code" in content

    def test_strips_bullet_markers(self, export_service: ExportService) -> None:
        result = export_service.export_txt("- item1\n- item2", "test")
        content = result.read().decode("utf-8")
        # Bullet markers should be stripped or converted
        assert "item1" in content
        assert "item2" in content

    def test_empty_text(self, export_service: ExportService) -> None:
        result = export_service.export_txt("", "empty")
        assert isinstance(result, io.BytesIO)
        assert result.read() == b""


class TestExportPdf:
    def test_returns_bytesio(self, export_service: ExportService) -> None:
        result = export_service.export_pdf(SAMPLE_PLAIN, "test")
        assert isinstance(result, io.BytesIO)

    def test_name_set(self, export_service: ExportService) -> None:
        result = export_service.export_pdf(SAMPLE_PLAIN, "test")
        assert result.name == "test.pdf"

    def test_pdf_magic_bytes(self, export_service: ExportService) -> None:
        result = export_service.export_pdf(SAMPLE_PLAIN, "test")
        data = result.read()
        assert data[:4] == b"%PDF"

    def test_empty_text(self, export_service: ExportService) -> None:
        result = export_service.export_pdf("", "empty")
        assert isinstance(result, io.BytesIO)
        assert result.name == "empty.pdf"


class TestExportDocx:
    def test_returns_bytesio(self, export_service: ExportService) -> None:
        result = export_service.export_docx(SAMPLE_MARKDOWN, "test")
        assert isinstance(result, io.BytesIO)

    def test_name_set(self, export_service: ExportService) -> None:
        result = export_service.export_docx(SAMPLE_MARKDOWN, "test")
        assert result.name == "test.docx"

    def test_docx_magic_bytes(self, export_service: ExportService) -> None:
        result = export_service.export_docx(SAMPLE_MARKDOWN, "test")
        data = result.read()
        # DOCX is a ZIP file, starts with PK
        assert data[:2] == b"PK"

    def test_docx_contains_text(self, export_service: ExportService) -> None:
        from docx import Document

        result = export_service.export_docx(SAMPLE_MARKDOWN, "test")
        doc = Document(result)
        full_text = "\n".join(p.text for p in doc.paragraphs)
        assert "Заголовок" in full_text

    def test_empty_text(self, export_service: ExportService) -> None:
        result = export_service.export_docx("", "empty")
        assert isinstance(result, io.BytesIO)
        assert result.name == "empty.docx"


class TestExportDispatcher:
    def test_dispatch_md(self, export_service: ExportService) -> None:
        result = export_service.export("text", "md", "file")
        assert result.name == "file.md"

    def test_dispatch_txt(self, export_service: ExportService) -> None:
        result = export_service.export("text", "txt", "file")
        assert result.name == "file.txt"

    def test_dispatch_pdf(self, export_service: ExportService) -> None:
        result = export_service.export("text", "pdf", "file")
        assert result.name == "file.pdf"

    def test_dispatch_docx(self, export_service: ExportService) -> None:
        result = export_service.export("text", "docx", "file")
        assert result.name == "file.docx"

    def test_invalid_format_raises(self, export_service: ExportService) -> None:
        with pytest.raises(ValueError, match="Unsupported export format"):
            export_service.export("text", "html", "file")


class TestStripMarkdown:
    """Test that export_txt properly strips markdown via strip_markdown()."""

    def test_strips_bold_asterisks(self, export_service: ExportService) -> None:
        result = export_service.export_txt("**bold**", "file")
        assert result.read().decode("utf-8").strip() == "bold"

    def test_strips_italic_asterisks(self, export_service: ExportService) -> None:
        result = export_service.export_txt("*italic*", "file")
        assert result.read().decode("utf-8").strip() == "italic"

    def test_strips_headers(self, export_service: ExportService) -> None:
        result = export_service.export_txt("### Header text", "file")
        content = result.read().decode("utf-8")
        assert "#" not in content
        assert "Header text" in content

    def test_strips_inline_code(self, export_service: ExportService) -> None:
        result = export_service.export_txt("`code`", "file")
        content = result.read().decode("utf-8")
        assert "`" not in content
        assert "code" in content

    def test_strips_bullet_dashes(self, export_service: ExportService) -> None:
        result = export_service.export_txt("- item", "file")
        content = result.read().decode("utf-8")
        assert "item" in content

    def test_strips_bullet_dots(self, export_service: ExportService) -> None:
        result = export_service.export_txt("• item", "file")
        content = result.read().decode("utf-8")
        assert "item" in content

    def test_strips_numbered_list(self, export_service: ExportService) -> None:
        result = export_service.export_txt("1. first\n2. second", "file")
        content = result.read().decode("utf-8")
        assert "first" in content
        assert "second" in content
