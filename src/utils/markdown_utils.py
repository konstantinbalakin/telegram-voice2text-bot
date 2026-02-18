"""Markdown utilities for Telegram MarkdownV2 formatting."""

import re
import logging

logger = logging.getLogger(__name__)

# MarkdownV2 special characters that must be escaped in plain text
MARKDOWNV2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"


def escape_markdownv2(text: str) -> str:
    """Escape MarkdownV2 special characters while preserving Markdown formatting.

    Converts standard Markdown formatting to Telegram MarkdownV2:
    - ``**bold**`` → ``*bold*``
    - ``*italic*`` → ``_italic_``
    - `` `code` `` preserved as-is
    - ````` ```code block``` ````` preserved as-is

    All other MarkdownV2 special characters in plain text are escaped with backslash.

    Args:
        text: Text with standard Markdown formatting

    Returns:
        Text ready for Telegram ``parse_mode="MarkdownV2"``
    """
    if not text:
        return text

    result: list[str] = []
    i = 0
    length = len(text)

    while i < length:
        # Code block: ```...```
        if text[i : i + 3] == "```":
            end = text.find("```", i + 3)
            if end != -1:
                result.append(text[i : end + 3])
                i = end + 3
                continue
            else:
                # No closing ```, escape backticks
                result.append(_escape_char("`"))
                result.append(_escape_char("`"))
                result.append(_escape_char("`"))
                i += 3
                continue

        # Inline code: `...`
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1 and "\n" not in text[i + 1 : end]:
                result.append(text[i : end + 1])
                i = end + 1
                continue
            else:
                result.append(_escape_char("`"))
                i += 1
                continue

        # Bold: **text**
        if text[i : i + 2] == "**":
            end = text.find("**", i + 2)
            if end != -1:
                inner = text[i + 2 : end]
                # MarkdownV2 bold = *text*
                result.append("*")
                result.append(_escape_plain_text(inner))
                result.append("*")
                i = end + 2
                continue
            else:
                # No closing **, escape both
                result.append(_escape_char("*"))
                result.append(_escape_char("*"))
                i += 2
                continue

        # Italic: *text* (single asterisk, not preceded by another *)
        if text[i] == "*" and (i == 0 or text[i - 1] != "*"):
            end = text.find("*", i + 1)
            if end != -1 and text[end : end + 2] != "**":
                inner = text[i + 1 : end]
                # MarkdownV2 italic = _text_
                result.append("_")
                result.append(_escape_plain_text(inner))
                result.append("_")
                i = end + 1
                continue
            else:
                result.append(_escape_char("*"))
                i += 1
                continue

        # Plain character — escape if special
        result.append(_escape_char(text[i]))
        i += 1

    return "".join(result)


def _escape_char(char: str) -> str:
    """Escape a single character if it's a MarkdownV2 special character."""
    if char in MARKDOWNV2_SPECIAL_CHARS:
        return f"\\{char}"
    return char


def _escape_plain_text(text: str) -> str:
    """Escape all MarkdownV2 special characters in plain text."""
    result: list[str] = []
    for char in text:
        result.append(_escape_char(char))
    return "".join(result)


def sanitize_markdown(text: str) -> str:
    """Clean text from HTML tags, converting supported ones to Markdown.

    Fallback for cases where LLM inserts HTML tags instead of Markdown.

    Converts:
    - ``<b>``/``<strong>`` → ``**text**``
    - ``<i>``/``<em>`` → ``*text*``
    - ``<code>`` → `` `text` ``
    - ``<pre>`` → `````text`````
    - ``<a href="url">text</a>`` → ``[text](url)``
    - ``<u>`` → strips tags (no Markdown equivalent)
    - Other tags → strips tags, keeps content

    Args:
        text: Text that may contain HTML tags

    Returns:
        Clean text with Markdown formatting
    """
    if not text:
        return text

    original = text

    # Convert supported HTML tags to Markdown
    # Bold: <b>, <strong>
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)

    # Italic: <i>, <em>
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<em>(.*?)</em>", r"*\1*", text, flags=re.DOTALL)

    # Code: <code>
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)

    # Pre: <pre>
    text = re.sub(r"<pre>(.*?)</pre>", r"```\n\1\n```", text, flags=re.DOTALL)

    # Links: <a href="url">text</a>
    text = re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL)

    # Strip remaining HTML tags (keep content)
    text = re.sub(r"<[^>]+>", "", text)

    # Clean up multiple consecutive newlines (max 2)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    text = text.strip()

    if text != original:
        logger.info(
            f"Sanitized markdown: {len(original)} → {len(text)} chars, " f"removed HTML tags"
        )

    return text


def strip_markdown(text: str) -> str:
    """Remove Markdown formatting to produce plain text.

    Preserves emojis and text content, removes all formatting markers.

    Strips: ``**bold**``, ``*italic*``, ``__underline__``, ``# headers``,
    `` `code` ``, ````` ```code blocks``` `````, ``- bullets``, ``• bullets``,
    numbered lists (``1.``, ``2.``, etc.)

    Args:
        text: Markdown-formatted text

    Returns:
        Plain text without Markdown markers, emojis preserved
    """
    if not text:
        return text

    result = text

    # Strip code blocks ```...```
    result = re.sub(r"```[^\n]*\n?(.*?)```", r"\1", result, flags=re.DOTALL)

    # Strip headers (# ## ### etc.)
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)

    # Strip bold **text** and __text__
    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
    result = re.sub(r"__(.+?)__", r"\1", result)

    # Strip italic *text* and _text_ (careful with underscores in words)
    result = re.sub(r"\*(.+?)\*", r"\1", result)
    result = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", result)

    # Strip inline code `text`
    result = re.sub(r"`(.+?)`", r"\1", result)

    # Strip bullet markers (- and •)
    result = re.sub(r"^[-•]\s+", "", result, flags=re.MULTILINE)

    # Strip numbered list markers (1. 2. etc.)
    result = re.sub(r"^\d+\.\s+", "", result, flags=re.MULTILINE)

    return result
