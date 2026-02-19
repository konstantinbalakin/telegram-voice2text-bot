"""Tests for src/utils/markdown_utils.py — MarkdownV2 utilities."""

from src.utils.markdown_utils import escape_markdownv2, sanitize_markdown, strip_markdown


# ============================================================
# Tests for escape_markdownv2()
# ============================================================


class TestEscapeMarkdownV2PlainText:
    """Escaping special chars in plain text (no formatting markers)."""

    def test_escapes_dot(self) -> None:
        assert escape_markdownv2("Конец.") == r"Конец\."

    def test_escapes_exclamation(self) -> None:
        assert escape_markdownv2("Привет!") == r"Привет\!"

    def test_escapes_parentheses(self) -> None:
        assert escape_markdownv2("(скобки)") == r"\(скобки\)"

    def test_escapes_brackets(self) -> None:
        assert escape_markdownv2("[квадратные]") == r"\[квадратные\]"

    def test_escapes_tilde(self) -> None:
        assert escape_markdownv2("~зачёркнутый~") == r"\~зачёркнутый\~"

    def test_escapes_hash(self) -> None:
        assert escape_markdownv2("#тег") == r"\#тег"

    def test_escapes_plus(self) -> None:
        assert escape_markdownv2("2+2") == r"2\+2"

    def test_escapes_minus(self) -> None:
        assert escape_markdownv2("пункт - дефис") == r"пункт \- дефис"

    def test_escapes_equals(self) -> None:
        assert escape_markdownv2("a=b") == r"a\=b"

    def test_escapes_pipe(self) -> None:
        assert escape_markdownv2("a|b") == r"a\|b"

    def test_escapes_curly_braces(self) -> None:
        assert escape_markdownv2("{json}") == r"\{json\}"

    def test_escapes_gt(self) -> None:
        assert escape_markdownv2("a > b") == r"a \> b"

    def test_escapes_multiple_specials(self) -> None:
        result = escape_markdownv2("Цена: 100$. Скидка!")
        assert r"\." in result
        assert r"\!" in result

    def test_empty_string(self) -> None:
        assert escape_markdownv2("") == ""

    def test_no_special_chars(self) -> None:
        assert escape_markdownv2("Привет мир") == "Привет мир"


class TestEscapeMarkdownV2PreservesFormatting:
    """Markdown formatting markers must be preserved (converted to MarkdownV2)."""

    def test_preserves_bold(self) -> None:
        result = escape_markdownv2("это **жирный** текст")
        # **bold** → *bold* in MarkdownV2
        assert "*жирный*" in result
        assert "**" not in result

    def test_preserves_italic(self) -> None:
        result = escape_markdownv2("это *курсив* текст")
        # *italic* → _italic_ in MarkdownV2
        assert "_курсив_" in result

    def test_preserves_inline_code(self) -> None:
        result = escape_markdownv2("используй `код` тут")
        assert "`код`" in result

    def test_preserves_code_block(self) -> None:
        result = escape_markdownv2("блок:\n```\ncode\n```")
        assert "```" in result

    def test_bold_with_special_chars_around(self) -> None:
        result = escape_markdownv2("Важно! **текст** (тут).")
        assert r"Важно\!" in result
        assert "*текст*" in result
        assert r"\(" in result
        assert r"\." in result

    def test_mixed_formatting(self) -> None:
        result = escape_markdownv2("**жирный** и *курсив* и `код`")
        assert "*жирный*" in result
        assert "_курсив_" in result
        assert "`код`" in result

    def test_nested_bold_italic_known_limitation(self) -> None:
        # Nested formatting (**bold *italic* inside**) is not fully supported.
        # Inner italic markers get escaped. Bold is still preserved.
        result = escape_markdownv2("**bold *italic* inside**")
        assert "*bold" in result  # Bold is converted


class TestEscapeMarkdownV2SpecExample:
    """Verification example from spec."""

    def test_spec_example(self) -> None:
        result = escape_markdownv2("Привет *мир*! Цена: 100$.")
        # *мир* (italic in std Markdown) → _мир_ in MarkdownV2
        assert "_мир_" in result
        assert r"\!" in result
        assert r"\." in result

    def test_emoji_preserved(self) -> None:
        result = escape_markdownv2("Привет 🎉 мир!")
        assert "🎉" in result
        assert r"\!" in result


class TestEscapeMarkdownV2EdgeCases:
    """Edge cases for escape_markdownv2."""

    def test_underscore_in_plain_text_escaped(self) -> None:
        # Standalone underscores (not part of formatting) should be escaped
        result = escape_markdownv2("my_variable_name")
        assert r"my\_variable\_name" == result

    def test_asterisk_in_plain_text_escaped(self) -> None:
        # Unmatched asterisks should be escaped
        result = escape_markdownv2("5 * 3 = 15")
        assert r"\*" in result
        assert r"\=" in result

    def test_backtick_in_plain_text_escaped(self) -> None:
        result = escape_markdownv2("это ` одиночный")
        assert r"\`" in result


# ============================================================
# Tests for sanitize_markdown()
# ============================================================


class TestSanitizeMarkdownRemovesHtml:
    """Remove HTML tags that LLM may accidentally insert."""

    def test_removes_bold_tag(self) -> None:
        assert sanitize_markdown("<b>текст</b>") == "**текст**"

    def test_removes_strong_tag(self) -> None:
        assert sanitize_markdown("<strong>текст</strong>") == "**текст**"

    def test_removes_italic_tag(self) -> None:
        assert sanitize_markdown("<i>текст</i>") == "*текст*"

    def test_removes_em_tag(self) -> None:
        assert sanitize_markdown("<em>текст</em>") == "*текст*"

    def test_removes_code_tag(self) -> None:
        assert sanitize_markdown("<code>код</code>") == "`код`"

    def test_removes_pre_tag(self) -> None:
        result = sanitize_markdown("<pre>блок кода</pre>")
        assert "```" in result
        assert "блок кода" in result

    def test_removes_underline_tag(self) -> None:
        # <u> has no direct Markdown equivalent, just strip tags
        assert sanitize_markdown("<u>подчёркнутый</u>") == "подчёркнутый"

    def test_removes_link_tag(self) -> None:
        result = sanitize_markdown('<a href="https://example.com">ссылка</a>')
        assert "[ссылка](https://example.com)" == result

    def test_strips_unsupported_tags(self) -> None:
        assert sanitize_markdown("<div>текст</div>") == "текст"

    def test_mixed_html_and_markdown(self) -> None:
        result = sanitize_markdown("<b>жирный</b> и **тоже жирный**")
        assert "**жирный**" in result
        assert "**тоже жирный**" in result

    def test_empty_string(self) -> None:
        assert sanitize_markdown("") == ""

    def test_no_html(self) -> None:
        text = "Обычный **текст** без HTML"
        assert sanitize_markdown(text) == text

    def test_nested_html_bold_italic(self) -> None:
        result = sanitize_markdown("<b>bold <i>italic</i></b>")
        assert "**bold *italic***" == result

    def test_multiple_newlines_cleaned(self) -> None:
        result = sanitize_markdown("первый\n\n\n\nвторой")
        assert "\n\n\n" not in result
        assert "первый" in result
        assert "второй" in result


# ============================================================
# Tests for strip_markdown()
# ============================================================


class TestStripMarkdownBasic:
    """Remove Markdown formatting to get plain text."""

    def test_strips_bold(self) -> None:
        assert strip_markdown("**жирный**") == "жирный"

    def test_strips_italic(self) -> None:
        assert strip_markdown("*курсив*") == "курсив"

    def test_strips_bold_and_italic(self) -> None:
        result = strip_markdown("**жирный** и *курсив*")
        assert result == "жирный и курсив"

    def test_strips_inline_code(self) -> None:
        assert strip_markdown("`код`") == "код"

    def test_strips_headers(self) -> None:
        result = strip_markdown("# Заголовок")
        assert "#" not in result
        assert "Заголовок" in result

    def test_strips_bullet_dash(self) -> None:
        result = strip_markdown("- пункт 1\n- пункт 2")
        assert "пункт 1" in result
        assert "пункт 2" in result
        assert "- " not in result

    def test_strips_bullet_dot(self) -> None:
        result = strip_markdown("• пункт 1\n• пункт 2")
        assert "пункт 1" in result
        assert "• " not in result

    def test_strips_numbered_list(self) -> None:
        result = strip_markdown("1. первый\n2. второй")
        assert "первый" in result
        assert "второй" in result

    def test_strips_underline_double_underscore(self) -> None:
        assert strip_markdown("__подчёркнутый__") == "подчёркнутый"


class TestStripMarkdownEmojis:
    """Emojis must be preserved in plain text."""

    def test_preserves_emoji(self) -> None:
        assert strip_markdown("текст 🎉 с эмодзи") == "текст 🎉 с эмодзи"

    def test_preserves_emoji_with_formatting(self) -> None:
        result = strip_markdown("**жирный** 🚀 *курсив* 😊")
        assert "жирный" in result
        assert "🚀" in result
        assert "курсив" in result
        assert "😊" in result
        assert "**" not in result
        assert "*" not in result

    def test_preserves_multiple_emojis(self) -> None:
        result = strip_markdown("👋 Привет! 🎉")
        assert "👋" in result
        assert "🎉" in result


class TestStripMarkdownEdgeCases:
    """Edge cases."""

    def test_empty_string(self) -> None:
        assert strip_markdown("") == ""

    def test_plain_text_unchanged(self) -> None:
        text = "Обычный текст без форматирования"
        assert strip_markdown(text) == text

    def test_code_block_stripped(self) -> None:
        result = strip_markdown("```\ncode block\n```")
        assert "```" not in result
        assert "code block" in result
