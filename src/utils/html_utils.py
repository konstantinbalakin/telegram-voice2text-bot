"""HTML utilities for Telegram message formatting."""

import re
import logging

logger = logging.getLogger(__name__)

# Telegram supported HTML tags (as of 2024)
TELEGRAM_ALLOWED_TAGS = {
    "b",
    "strong",  # Bold
    "i",
    "em",  # Italic
    "u",
    "ins",  # Underline
    "s",
    "strike",
    "del",  # Strikethrough
    "code",  # Inline code
    "pre",  # Code block
    "a",  # Links (with href attribute)
}

# Tags to remove completely (including content)
REMOVE_TAGS: set[str] = set()

# Tags to strip (remove tag but keep content)
STRIP_TAGS = {
    "p",
    "div",
    "span",
    "br",  # Block/inline elements
    "ul",
    "ol",
    "li",  # Lists
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",  # Headers
    "table",
    "tr",
    "td",
    "th",
    "tbody",
    "thead",  # Tables
    "blockquote",
    "cite",
    "q",  # Quotes
    "sup",
    "sub",  # Superscript/subscript
    "mark",
    "small",  # Text modifiers
}


def sanitize_html(html: str) -> str:
    """
    Sanitize HTML to only contain Telegram-supported tags.

    This function removes or strips unsupported HTML tags to ensure
    the text can be safely sent via Telegram API with parse_mode="HTML".

    Args:
        html: HTML string to sanitize

    Returns:
        Sanitized HTML string with only Telegram-supported tags

    Example:
        >>> sanitize_html("<p>Hello <b>world</b></p>")
        "Hello <b>world</b>"

        >>> sanitize_html("<ul><li>Item 1</li><li>Item 2</li></ul>")
        "Item 1Item 2"
    """
    if not html:
        return html

    # Track if any changes were made
    original_html = html

    # Step 1: Remove tags that should be stripped (keep content)
    for tag in STRIP_TAGS:
        # Remove opening and closing tags, keep content
        # Case insensitive matching
        html = re.sub(rf"<{tag}[^>]*?>", "", html, flags=re.IGNORECASE)
        html = re.sub(rf"</{tag}>", "", html, flags=re.IGNORECASE)

    # Step 2: Remove tags that should be deleted (including content)
    for tag in REMOVE_TAGS:
        # Remove tag with all its content
        html = re.sub(rf"<{tag}[^>]*?>.*?</{tag}>", "", html, flags=re.IGNORECASE | re.DOTALL)

    # Step 3: Clean up any remaining unsupported tags
    # This catches any tags we might have missed
    def replace_tag(match: re.Match[str]) -> str:
        tag_name = match.group(2).lower()  # Tag name

        if tag_name in TELEGRAM_ALLOWED_TAGS:
            return match.group(0)  # Keep supported tags
        else:
            logger.debug(f"Stripping unsupported tag: {tag_name}")
            return ""  # Remove unsupported tags

    # Match any HTML tag
    html = re.sub(r"<(/?)(\w+)([^>]*?)>", replace_tag, html)

    # Step 4: Clean up multiple consecutive spaces/newlines
    html = re.sub(r"\n\s*\n\s*\n+", "\n\n", html)  # Max 2 newlines
    html = re.sub(r"[ \t]+", " ", html)  # Multiple spaces to single space

    # Step 5: Trim whitespace
    html = html.strip()

    # Log if changes were made
    if html != original_html:
        logger.info(
            f"Sanitized HTML: {len(original_html)} → {len(html)} chars, "
            f"removed unsupported tags"
        )

    return html


def escape_html(text: str) -> str:
    """
    Escape special HTML characters.

    Use this for plain text that needs to be included in HTML-formatted messages.

    Args:
        text: Plain text to escape

    Returns:
        HTML-escaped text
    """
    if not text:
        return text

    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }

    for char, escape in replacements.items():
        text = text.replace(char, escape)

    return text
