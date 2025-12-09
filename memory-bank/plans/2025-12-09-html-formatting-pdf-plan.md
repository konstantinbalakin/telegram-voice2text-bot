# HTML Formatting and PDF Generation Plan

**Created**: 2025-12-09
**Status**: In Progress
**Branch**: `feature/html-formatting-pdf`

## Problem Statement

LLM returns text with Markdown formatting (`**текст**`), but Telegram displays it literally without rendering. Users see raw Markdown syntax instead of formatted text. For large transcriptions (>3000 chars), text files (.txt) are generated without any formatting preservation.

## Approved Solution: Variant 1 (WeasyPrint + HTML)

### Key Decisions

- **Formatting**: Use HTML with `parse_mode="HTML"` for Telegram
- **PDF Library**: WeasyPrint (HTML-to-PDF conversion)
- **No Migration**: Existing cached variants remain as-is
- **No Custom CSS**: Use default styling initially ("может потом улучшим")
- **Supported Formatting**: All Telegram-supported HTML tags (bold, italic, underline, links, lists, code blocks, headers)

### WeasyPrint Advantages

- **HTML Native**: Direct HTML string → PDF conversion
- **Best Quality**: Professional typography and layout
- **Cyrillic Support**: Built-in Unicode/Cyrillic rendering
- **Simple API**: `HTML(string='...').write_pdf()` returns bytes
- **FontConfiguration**: Support for custom fonts if needed

### Trade-offs Accepted

- **Docker Image**: ~100MB increase (system dependencies: Cairo, Pango)
- **Complexity**: Medium (HTML template management)
- **Dependencies**: System packages required in Docker

## Implementation Phases

### Phase 1: Dependency Setup ✅

**Files**:
- `pyproject.toml` - Add WeasyPrint dependency
- `Dockerfile` - Install system dependencies

**System Dependencies** (Debian/Ubuntu):
```dockerfile
libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

**Python Dependency**:
```toml
weasyprint = "^62.3"
```

### Phase 2: PDF Generator Module

**Create**: `src/services/pdf_generator.py`

**Class**: `PDFGenerator`

**Methods**:
- `generate_pdf(html_content: str) -> bytes` - Convert HTML to PDF
- `create_styled_html(text: str) -> str` - Wrap content in HTML template

**HTML Template**:
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            font-size: 12pt;
            line-height: 1.6;
            padding: 20px;
        }
    </style>
</head>
<body>{content}</body>
</html>
```

**Error Handling**:
- Graceful fallback to .txt if PDF generation fails
- Logging for debugging

### Phase 3: Update LLM Prompts for HTML Output

**Files to Update**:
1. `prompts/structured.md` - Main structured mode
2. `prompts/summary.md` - Summary generation
3. `prompts/emoji.md` - Emoji mode
4. `prompts/length_short.md` - Short length mode
5. `prompts/refinement.md` - Refinement mode

**HTML Tags to Use**:
- `<b>text</b>` - Bold
- `<i>text</i>` - Italic
- `<u>text</u>` - Underline
- `<code>text</code>` - Monospace
- `<pre>code</pre>` - Code block
- `<ul><li>item</li></ul>` - Unordered list
- `<ol><li>item</li></ol>` - Ordered list
- `<a href="url">text</a>` - Links

**Example Update** (structured.md):
```markdown
## Форматирование HTML

Используй HTML-теги для форматирования:
- Заголовки: <b>Заголовок</b>
- Списки: <ul><li>пункт</li></ul>
- Важные моменты: <b>жирный текст</b>
- Примечания: <i>курсив</i>
```

### Phase 4: Add parse_mode="HTML" to Message Sending

**Files to Update**:

**`src/bot/callbacks.py`**:
- Line 85: `query.edit_message_text()` - Add `parse_mode="HTML"`
- Line 102: Caption update - Add `parse_mode="HTML"`
- Line 189: File→text conversion - Add `parse_mode="HTML"`

**`src/bot/handlers.py`**:
- Line 1136: Initial result - Add `parse_mode="HTML"`
- Line 1187: Draft message - Add `parse_mode="HTML"`
- Line 568: Benchmark - Change from `"Markdown"` to `"HTML"`
- Line 1370: Debug mode - Already uses HTML ✅

### Phase 5: Integrate PDF Generation for Large Files

**Files to Update**:
- `src/bot/callbacks.py` (lines 156-157)
- `src/bot/handlers.py` (file creation logic)

**Logic**:
```python
if len(new_text) > FILE_THRESHOLD_CHARS:
    try:
        # Generate PDF
        pdf_generator = PDFGenerator()
        html_content = pdf_generator.create_styled_html(new_text)
        pdf_bytes = pdf_generator.generate_pdf(html_content)

        file_obj = io.BytesIO(pdf_bytes)
        file_obj.name = f"transcription_{usage_id}_{mode}.pdf"
    except Exception as e:
        logger.error(f"PDF generation failed: {e}, falling back to TXT")
        # Fallback to TXT
        file_obj = io.BytesIO(new_text.encode("utf-8"))
        file_obj.name = f"transcription_{usage_id}_{mode}.txt"
else:
    # Send as message with HTML formatting
    await context.bot.send_message(
        chat_id=chat_id,
        text=new_text,
        parse_mode="HTML"
    )
```

**Configuration**:
- Use existing `FILE_THRESHOLD_CHARS=3000` from `src/config.py:226`

### Phase 6: Testing

**Unit Tests**: Create `tests/services/test_pdf_generator.py`

**Test Cases**:
1. Basic HTML to PDF conversion
2. Cyrillic text rendering
3. HTML tags (bold, italic, lists)
4. Error handling (invalid HTML)
5. Memory efficiency (large texts)

**Integration Tests**:
1. End-to-end: Voice → Transcription → HTML formatting → Telegram display
2. End-to-end: Large file → PDF generation → Telegram file delivery
3. Fallback: PDF failure → TXT delivery

**Manual Testing**:
1. Send short voice message → Check HTML formatting in Telegram
2. Send long voice message → Check PDF file generation
3. Test all transcription modes (structured, summary, emoji, etc.)

## Dependencies Verification (Context7)

**Library**: `/kozea/weasyprint`
- **Benchmark Score**: 85.3
- **Reputation**: High
- **Documentation**: `/websites/doc_courtbouillon_weasyprint_stable` (284 code snippets)

**API Confirmed**:
```python
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

# Basic usage
pdf_bytes = HTML(string='<h1>Hello</h1>').write_pdf()

# With custom fonts
font_config = FontConfiguration()
html = HTML(string='<h1>Title</h1>')
css = CSS(string='body { font-family: "DejaVu Sans"; }', font_config=font_config)
html.write_pdf('/tmp/example.pdf', stylesheets=[css], font_config=font_config)
```

## Rollback Plan

If issues arise:
1. **Revert parse_mode**: Remove `parse_mode="HTML"` from message sending
2. **Disable PDF**: Keep .txt file generation
3. **Revert Prompts**: Restore original prompt files
4. **Remove Dependencies**: Uninstall WeasyPrint from Docker

## Future Improvements

- Custom CSS styling for PDFs
- Font selection (serif, sans-serif)
- Page layout options (margins, page size)
- Watermarks or headers/footers
- PDF compression for smaller file sizes

## References

- [Telegram Bot API: Formatting Options](https://core.telegram.org/bots/api#formatting-options)
- [WeasyPrint Documentation](https://doc.courtbouillon.org/weasyprint/stable/)
- [python-telegram-bot v22.5](https://docs.python-telegram-bot.org/)
