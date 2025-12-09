"""PDF generation service using WeasyPrint."""

import logging

from weasyprint import HTML  # type: ignore[import-untyped]
from weasyprint.text.fonts import FontConfiguration  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Service for generating PDF files from HTML content."""

    def __init__(self) -> None:
        """Initialize PDF generator with font configuration."""
        self.font_config = FontConfiguration()

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
            line-height: 1.6;
            padding: 20px;
            color: #333;
        }}
        h1, h2, h3 {{
            margin-top: 1em;
            margin-bottom: 0.5em;
        }}
        ul, ol {{
            margin: 0.5em 0;
            padding-left: 2em;
        }}
        li {{
            margin: 0.3em 0;
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

        Args:
            html_content: HTML content to convert to PDF

        Returns:
            PDF file as bytes

        Raises:
            Exception: If PDF generation fails
        """
        try:
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

    def generate_pdf_from_text(
        self, text: str, wrap_paragraphs: bool = True
    ) -> bytes:
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
