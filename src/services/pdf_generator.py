"""PDF generation service using WeasyPrint."""

import logging
import re

from weasyprint import HTML  # type: ignore[import-untyped]
from weasyprint.text.fonts import FontConfiguration  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


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

    def generate_pdf(self, html_content: str) -> bytes:
        """
        Generate PDF from HTML content.

        Automatically converts text formatting (bullets, paragraphs) to HTML structure.

        Args:
            html_content: HTML content or plain text with formatting to convert to PDF

        Returns:
            PDF file as bytes

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Convert text formatting to HTML if needed
            # This handles cases where content has bullets (•) and paragraphs
            # but not proper HTML tags
            if (
                "<ul>" not in html_content
                and "<ol>" not in html_content
                and "<p>" not in html_content
            ):
                html_content = self.convert_text_to_html(html_content)

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
        Generate PDF from plain text (not HTML).

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
                # Split by double newlines for paragraphs
                paragraphs = text.split("\n\n")
                html_content = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
            else:
                html_content = text

            return self.generate_pdf(html_content)

        except Exception as e:
            logger.error(f"Failed to generate PDF from text: {e}", exc_info=True)
            raise
