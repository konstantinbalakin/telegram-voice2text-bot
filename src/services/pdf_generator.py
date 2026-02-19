"""PDF generation service using WeasyPrint."""

from __future__ import annotations

import io
import logging
import re
from typing import Optional

from weasyprint import HTML  # type: ignore[import-untyped]
from weasyprint.text.fonts import FontConfiguration  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_pdf_generator: PDFGenerator | None = None


def _get_pdf_generator() -> PDFGenerator:
    """Get or create the singleton PDFGenerator instance."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGenerator()
    return _pdf_generator


def convert_markdown_to_html(text: str) -> str:
    """Convert Markdown-formatted text to HTML for PDF rendering.

    Supports: headings, bold, italic, inline code, code blocks,
    bullet lists (- and •), numbered lists, links, paragraphs.

    Args:
        text: Text with standard Markdown formatting

    Returns:
        HTML string suitable for PDF rendering
    """
    if not text:
        return text

    result = text

    # Code blocks: ```...``` → <pre><code>...</code></pre>
    result = re.sub(
        r"```[^\n]*\n(.*?)```",
        r"<pre><code>\1</code></pre>",
        result,
        flags=re.DOTALL,
    )

    # Inline code: `text` → <code>text</code>
    result = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", result)

    # Bold: **text** → <strong>text</strong>
    result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", result)

    # Italic: *text* → <em>text</em>
    result = re.sub(r"\*(.+?)\*", r"<em>\1</em>", result)

    # Underline: __text__ → <u>text</u>
    result = re.sub(r"__(.+?)__", r"<u>\1</u>", result)

    # Links: [text](url) → <a href="url">text</a>
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', result)

    # Headings: # text → <h1>text</h1>, ## → h2, ### → h3
    result = re.sub(r"^### (.+)$", r"<h3>\1</h3>", result, flags=re.MULTILINE)
    result = re.sub(r"^## (.+)$", r"<h2>\1</h2>", result, flags=re.MULTILINE)
    result = re.sub(r"^# (.+)$", r"<h1>\1</h1>", result, flags=re.MULTILINE)

    # Process blocks: split by double newlines for paragraphs/lists
    blocks = result.split("\n\n")
    html_blocks: list[str] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Skip blocks that are already HTML elements
        if block.startswith(("<h1>", "<h2>", "<h3>", "<pre>")):
            html_blocks.append(block)
            continue

        lines = block.split("\n")

        # Bullet list (• or -)
        if any(re.match(r"^\s*[•\-]\s+", line) for line in lines):
            list_items: list[str] = []
            for line in lines:
                line = line.strip()
                match = re.match(r"^[•\-]\s+(.*)", line)
                if match:
                    list_items.append(f"<li>{match.group(1)}</li>")
                elif line and list_items:
                    list_items[-1] = list_items[-1][:-5] + " " + line + "</li>"
            if list_items:
                html_blocks.append("<ul>" + "".join(list_items) + "</ul>")

        # Numbered list
        elif any(re.match(r"^\d+\.", line.strip()) for line in lines):
            list_items = []
            for line in lines:
                line = line.strip()
                match = re.match(r"^\d+\.\s*(.*)", line)
                if match:
                    list_items.append(f"<li>{match.group(1).strip()}</li>")
                elif line and list_items:
                    list_items[-1] = list_items[-1][:-5] + " " + line + "</li>"
            if list_items:
                html_blocks.append("<ol>" + "".join(list_items) + "</ol>")

        # Regular paragraph
        else:
            paragraph_text = "<br>".join(lines)
            html_blocks.append(f"<p>{paragraph_text}</p>")

    return "".join(html_blocks)


class PDFGenerator:
    """Service for generating PDF files from HTML content."""

    def __init__(self) -> None:
        """Initialize PDF generator with font configuration."""
        self.font_config = FontConfiguration()

    def convert_text_to_html(self, text: str) -> str:
        """
        Convert plain text with bullet points to HTML structure.

        Converts:
        - Paragraphs (double newlines) → <p>...</p>
        - Bullet lists (• symbol) → <ul><li>...</li></ul>
        - Numbered lists (1., 2., etc.) → <ol><li>...</li></ol>

        Args:
            text: Plain text with text formatting (bullets, paragraphs)

        Returns:
            HTML-formatted text
        """
        if not text:
            return text

        # Split into blocks by double newlines
        blocks = text.split("\n\n")
        html_blocks = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")

            # Check if this is a bullet list (• symbol)
            if any(line.strip().startswith("•") for line in lines):
                list_items = []
                for line in lines:
                    line = line.strip()
                    if line.startswith("•"):
                        # Remove bullet and trim
                        item_text = line[1:].strip()
                        list_items.append(f"<li>{item_text}</li>")
                    elif line and list_items:
                        # Continuation of previous item
                        list_items[-1] = list_items[-1][:-5] + " " + line + "</li>"

                if list_items:
                    html_blocks.append("<ul>" + "".join(list_items) + "</ul>")

            # Check if this is a numbered list (1., 2., etc.)
            elif any(re.match(r"^\d+\.", line.strip()) for line in lines):
                list_items = []
                for line in lines:
                    line = line.strip()
                    match = re.match(r"^\d+\.\s*(.*)", line)
                    if match:
                        item_text = match.group(1).strip()
                        list_items.append(f"<li>{item_text}</li>")
                    elif line and list_items:
                        # Continuation of previous item
                        list_items[-1] = list_items[-1][:-5] + " " + line + "</li>"

                if list_items:
                    html_blocks.append("<ol>" + "".join(list_items) + "</ol>")

            # Regular paragraph
            else:
                # Join lines with <br> for single newlines within paragraph
                paragraph_text = "<br>".join(lines)
                html_blocks.append(f"<p>{paragraph_text}</p>")

        return "".join(html_blocks)

    def create_styled_html(self, content: str) -> str:
        """
        Wrap content in HTML template with basic styling.

        Args:
            content: HTML content to wrap

        Returns:
            Complete HTML document with styling
        """
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            font-size: 12pt;
            line-height: 1.8;
            padding: 20px;
            color: #333;
        }}
        h1, h2, h3 {{
            margin-top: 1.5em;
            margin-bottom: 0.8em;
        }}
        p {{
            margin: 0 0 1.2em 0;
        }}
        ul, ol {{
            margin: 1em 0;
            padding-left: 2em;
        }}
        li {{
            margin: 0.5em 0;
        }}
        code {{
            background-color: #f4f4f4;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: monospace;
        }}
        pre {{
            background-color: #f4f4f4;
            padding: 1em;
            border-radius: 5px;
            overflow-x: auto;
            margin: 1em 0;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
{content}
</body>
</html>"""
        return html_template

    def generate_pdf(self, text: str) -> bytes:
        """
        Generate PDF from text content (Markdown or plain text).

        Automatically converts Markdown formatting to HTML for PDF rendering.

        Args:
            text: Markdown-formatted or plain text content to convert to PDF

        Returns:
            PDF file as bytes

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Convert Markdown to HTML for rendering
            html_content = convert_markdown_to_html(text)

            # Create styled HTML document
            styled_html = self.create_styled_html(html_content)

            # Generate PDF
            html_obj = HTML(string=styled_html)
            pdf_bytes: bytes = html_obj.write_pdf(font_config=self.font_config)  # type: ignore[assignment]

            logger.info("PDF generated successfully")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}", exc_info=True)
            raise

    def generate_pdf_from_text(self, text: str, wrap_paragraphs: bool = True) -> bytes:
        """
        Generate PDF from plain text (not Markdown).

        Wraps text in HTML paragraphs directly, bypassing Markdown-to-HTML conversion.

        Args:
            text: Plain text content
            wrap_paragraphs: If True, wraps text in <p> tags

        Returns:
            PDF file as bytes

        Raises:
            Exception: If PDF generation fails
        """
        try:
            if wrap_paragraphs:
                paragraphs = text.split("\n\n")
                html_content = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
            else:
                html_content = f"<p>{text}</p>"

            styled_html = self.create_styled_html(html_content)
            html_obj = HTML(string=styled_html)
            pdf_bytes: bytes = html_obj.write_pdf(font_config=self.font_config)  # type: ignore[assignment]

            logger.info("PDF generated from text successfully")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate PDF from text: {e}", exc_info=True)
            raise


def create_file_object(
    text: str,
    filename_prefix: str,
    pdf_generator: Optional[PDFGenerator] = None,
) -> tuple[io.BytesIO, str]:
    """Create a file object (PDF with TXT fallback) for sending via Telegram.

    Args:
        text: Text content for the file
        filename_prefix: Prefix for the filename (e.g. "1_original")
        pdf_generator: Optional PDFGenerator instance (created if not provided)

    Returns:
        Tuple of (file BytesIO object with .name set, file extension string "PDF" or "TXT")
    """
    try:
        gen = pdf_generator or _get_pdf_generator()
        pdf_bytes = gen.generate_pdf(text)
        file_obj = io.BytesIO(pdf_bytes)
        file_obj.name = f"{filename_prefix}.pdf"
        return file_obj, "PDF"
    except Exception as e:
        logger.warning(f"PDF generation failed, falling back to TXT: {e}")
        file_obj = io.BytesIO(text.encode("utf-8"))
        file_obj.name = f"{filename_prefix}.txt"
        return file_obj, "TXT"
