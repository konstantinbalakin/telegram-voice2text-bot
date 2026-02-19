"""Tests for download callback handlers in src/bot/callbacks.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.callbacks import CallbackHandlers
from src.services.export_service import ExportService
from tests.helpers import make_query, make_update, make_state, make_variant, make_usage, make_user


@pytest.fixture
def repos() -> tuple:
    """Create mock repositories."""
    state_repo = AsyncMock()
    variant_repo = AsyncMock()
    segment_repo = AsyncMock()
    usage_repo = AsyncMock()
    user_repo = AsyncMock()
    return state_repo, variant_repo, segment_repo, usage_repo, user_repo


@pytest.fixture
def export_service() -> ExportService:
    return ExportService()


@pytest.fixture
def handler(repos: tuple, export_service: ExportService) -> CallbackHandlers:
    """Create a CallbackHandlers instance with mock repos and ExportService."""
    state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
    return CallbackHandlers(
        state_repo=state_repo,
        variant_repo=variant_repo,
        segment_repo=segment_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
        export_service=export_service,
    )


# ---------------------------------------------------------------------------
# handle_download_menu
# ---------------------------------------------------------------------------


class TestHandleDownloadMenu:
    async def test_shows_format_submenu(self, handler: CallbackHandlers, repos: tuple) -> None:
        """Pressing "Скачать" should replace keyboard with format submenu."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download:42")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        user_repo.get_by_id = AsyncMock(return_value=make_user())

        await handler.handle_download_menu(update, context)

        query.answer.assert_called()
        query.edit_message_text.assert_called_once()
        call_kwargs = query.edit_message_text.call_args
        # Should have reply_markup with download format keyboard
        assert call_kwargs.kwargs.get("reply_markup") is not None

    async def test_state_not_found(self, handler: CallbackHandlers, repos: tuple) -> None:
        """If state not found, should show error."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download:42")
        update = make_update(query)
        context = AsyncMock()

        state_repo.get_by_usage_id = AsyncMock(return_value=None)

        await handler.handle_download_menu(update, context)

        query.answer.assert_called_with("Состояние не найдено", show_alert=True)


# ---------------------------------------------------------------------------
# handle_download_format
# ---------------------------------------------------------------------------


class TestHandleDownloadFormat:
    async def test_sends_file_txt(self, handler: CallbackHandlers, repos: tuple) -> None:
        """Selecting TXT format should send a .txt document."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=txt")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("Hello world")
        variant_repo.get_variant = AsyncMock(return_value=variant)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        await handler.handle_download_format(update, context)

        context.bot.send_document.assert_called_once()
        call_kwargs = context.bot.send_document.call_args
        sent_doc = (
            call_kwargs.kwargs.get("document") or call_kwargs.args[0]
            if call_kwargs.args
            else call_kwargs.kwargs["document"]
        )
        assert hasattr(sent_doc, "name")
        assert sent_doc.name.endswith(".txt")

    async def test_sends_file_md(self, handler: CallbackHandlers, repos: tuple) -> None:
        """Selecting MD format should send a .md document."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=md")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("# Hello")
        variant_repo.get_variant = AsyncMock(return_value=variant)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        await handler.handle_download_format(update, context)

        context.bot.send_document.assert_called_once()
        call_kwargs = context.bot.send_document.call_args
        sent_doc = call_kwargs.kwargs["document"]
        assert sent_doc.name.endswith(".md")

    async def test_sends_file_pdf(self, handler: CallbackHandlers, repos: tuple) -> None:
        """Selecting PDF format should send a .pdf document."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=pdf")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("Hello world")
        variant_repo.get_variant = AsyncMock(return_value=variant)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        await handler.handle_download_format(update, context)

        context.bot.send_document.assert_called_once()
        call_kwargs = context.bot.send_document.call_args
        sent_doc = call_kwargs.kwargs["document"]
        assert sent_doc.name.endswith(".pdf")

    async def test_sends_file_docx(self, handler: CallbackHandlers, repos: tuple) -> None:
        """Selecting DOCX format should send a .docx document."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=docx")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("Hello world")
        variant_repo.get_variant = AsyncMock(return_value=variant)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        await handler.handle_download_format(update, context)

        context.bot.send_document.assert_called_once()
        call_kwargs = context.bot.send_document.call_args
        sent_doc = call_kwargs.kwargs["document"]
        assert sent_doc.name.endswith(".docx")

    @patch("src.bot.callbacks.settings")
    async def test_restores_text_and_keyboard_after_send(
        self, mock_settings: MagicMock, handler: CallbackHandlers, repos: tuple
    ) -> None:
        """After sending file, should restore both text and main keyboard."""
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_structured_mode = True
        mock_settings.enable_magic_mode = True
        mock_settings.enable_summary_mode = True
        mock_settings.enable_length_variations = False
        mock_settings.enable_emoji_option = False
        mock_settings.enable_timestamps_option = False
        mock_settings.enable_download_button = True
        mock_settings.file_threshold_chars = 10000
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=txt")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("Hello world")
        variant_repo.get_variant = AsyncMock(return_value=variant)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        segment_repo.get_by_usage_id = AsyncMock(return_value=[])

        await handler.handle_download_format(update, context)

        # edit_message_text should be called to restore text AND keyboard
        query.edit_message_text.assert_called()
        call_kwargs = query.edit_message_text.call_args
        assert call_kwargs.kwargs.get("reply_markup") is not None
        assert "Hello world" in call_kwargs.args[0]

    async def test_variant_not_found(self, handler: CallbackHandlers, repos: tuple) -> None:
        """If variant not found, should show error."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=txt")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant_repo.get_variant = AsyncMock(return_value=None)

        await handler.handle_download_format(update, context)

        query.answer.assert_called_with("Текст не найден", show_alert=True)

    async def test_no_export_service(self, repos: tuple) -> None:
        """If no export_service provided, should show error."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        handler_no_export = CallbackHandlers(
            state_repo=state_repo,
            variant_repo=variant_repo,
            segment_repo=segment_repo,
            usage_repo=usage_repo,
            user_repo=user_repo,
            export_service=None,
        )
        query = make_query("download_fmt:42:fmt=txt")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("Hello world")
        variant_repo.get_variant = AsyncMock(return_value=variant)

        await handler_no_export.handle_download_format(update, context)

        query.answer.assert_called_with("Экспорт недоступен", show_alert=True)


class TestHandleDownloadFormatErrors:
    """Test error paths in handle_download_format."""

    async def test_export_error_shows_alert(self, handler: CallbackHandlers, repos: tuple) -> None:
        """When export_service.export raises, user should see an error alert."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=pdf")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        variant = make_variant("Hello world")
        variant_repo.get_variant = AsyncMock(return_value=variant)
        usage_repo.get_by_id = AsyncMock(return_value=make_usage())
        usage_repo.count_by_user_id = AsyncMock(return_value=5)
        user_repo.get_by_id = AsyncMock(return_value=make_user())

        with patch.object(
            handler.export_service, "export", side_effect=Exception("PDF generation failed")
        ):
            await handler.handle_download_format(update, context)

        assert any("Не удалось создать файл" in str(c) for c in query.answer.call_args_list)
        context.bot.send_document.assert_not_called()

    async def test_state_not_found(self, handler: CallbackHandlers, repos: tuple) -> None:
        """When state is not found, should show error."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download_fmt:42:fmt=txt")
        update = make_update(query)
        context = AsyncMock()

        state_repo.get_by_usage_id = AsyncMock(return_value=None)

        await handler.handle_download_format(update, context)

        query.answer.assert_called_with("Состояние не найдено", show_alert=True)


class TestHandleDownloadMenuErrors:
    """Test error paths in handle_download_menu."""

    async def test_edit_message_error_shows_alert(
        self, handler: CallbackHandlers, repos: tuple
    ) -> None:
        """When edit_message_text fails, should answer with error."""
        state_repo, variant_repo, segment_repo, usage_repo, user_repo = repos
        query = make_query("download:42")
        update = make_update(query)
        context = AsyncMock()

        state = make_state(usage_id=42)
        state_repo.get_by_usage_id = AsyncMock(return_value=state)
        query.edit_message_text = AsyncMock(side_effect=Exception("Telegram error"))

        await handler.handle_download_menu(update, context)

        assert any("Не удалось показать меню" in str(c) for c in query.answer.call_args_list)
