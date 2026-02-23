"""Tests for TranscriptionOrchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.queue_manager import TranscriptionRequest
from src.services.transcription_orchestrator import (
    TranscriptionOrchestrator,
    save_audio_file_for_retranscription,
)
from src.transcription.models import (
    TranscriptionContext,
    TranscriptionResult,
    TranscriptionSegment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    request_id: str = "req-1",
    user_id: int = 100,
    duration_seconds: int = 30,
    usage_id: int = 1,
    disable_refinement: bool = False,
) -> TranscriptionRequest:
    """Create a TranscriptionRequest with mocked Telegram objects."""
    status_message = AsyncMock()
    status_message.delete = AsyncMock()
    status_message.edit_text = AsyncMock()

    user_message = AsyncMock()
    user_message.chat_id = 12345
    user_message.reply_text = AsyncMock(return_value=AsyncMock(message_id=999))
    user_message.reply_document = AsyncMock(return_value=AsyncMock(message_id=1000))

    return TranscriptionRequest(
        id=request_id,
        user_id=user_id,
        file_path=Path("/tmp/test_audio.ogg"),
        duration_seconds=duration_seconds,
        context=TranscriptionContext(
            user_id=user_id,
            duration_seconds=duration_seconds,
            disable_refinement=disable_refinement,
        ),
        status_message=status_message,
        user_message=user_message,
        usage_id=usage_id,
    )


def _make_result(
    text: str = "Transcribed text",
    language: str = "ru",
    processing_time: float = 1.5,
    audio_duration: float = 30.0,
    provider_used: str = "openai",
    model_name: str = "whisper-1",
    segments: list | None = None,
) -> TranscriptionResult:
    """Create a TranscriptionResult."""
    return TranscriptionResult(
        text=text,
        language=language,
        processing_time=processing_time,
        audio_duration=audio_duration,
        provider_used=provider_used,
        model_name=model_name,
        segments=segments,
    )


def _make_orchestrator(
    router: MagicMock | None = None,
    audio_handler: MagicMock | None = None,
    llm_service: MagicMock | None = None,
    text_processor: MagicMock | None = None,
) -> TranscriptionOrchestrator:
    """Create an orchestrator with mocked dependencies."""
    if router is None:
        router = MagicMock()
        router.transcribe = AsyncMock(return_value=_make_result())
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = MagicMock()
    if audio_handler is None:
        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()
    return TranscriptionOrchestrator(
        transcription_router=router,
        audio_handler=audio_handler,
        llm_service=llm_service,
        text_processor=text_processor,
    )


def _mock_session_ctx():
    """Create mock for get_session() async context manager."""
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


# ---------------------------------------------------------------------------
# Tests: save_audio_file_for_retranscription
# ---------------------------------------------------------------------------


class TestSaveAudioFileForRetranscription:
    """Tests for the save_audio_file_for_retranscription function."""

    @patch("src.services.transcription_orchestrator.settings")
    def test_disabled_returns_none(self, mock_settings):
        mock_settings.enable_retranscribe = False
        result = save_audio_file_for_retranscription(Path("/tmp/a.ogg"), 1, "abc")
        assert result is None

    @patch("src.services.transcription_orchestrator.settings")
    def test_success_copies_file(self, mock_settings, tmp_path):
        mock_settings.enable_retranscribe = True
        mock_settings.persistent_audio_dir = str(tmp_path / "persistent")

        src_file = tmp_path / "source.ogg"
        src_file.write_bytes(b"fake audio data")

        result = save_audio_file_for_retranscription(src_file, 1, "file123")

        assert result is not None
        assert result.exists()
        assert result.suffix == ".ogg"
        assert result.read_bytes() == b"fake audio data"

    @patch("src.services.transcription_orchestrator.settings")
    def test_creates_directory(self, mock_settings, tmp_path):
        mock_settings.enable_retranscribe = True
        target_dir = tmp_path / "new_dir" / "subdir"
        mock_settings.persistent_audio_dir = str(target_dir)

        src_file = tmp_path / "source.ogg"
        src_file.write_bytes(b"data")

        result = save_audio_file_for_retranscription(src_file, 1, "f1")
        assert result is not None
        assert target_dir.exists()

    @patch("src.services.transcription_orchestrator.shutil.copy2", side_effect=OSError("disk full"))
    @patch("src.services.transcription_orchestrator.settings")
    def test_copy_failure_returns_none(self, mock_settings, _mock_copy, tmp_path):
        mock_settings.enable_retranscribe = True
        mock_settings.persistent_audio_dir = str(tmp_path / "persistent")

        result = save_audio_file_for_retranscription(Path("/tmp/a.ogg"), 1, "abc")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestOrchestratorInit:
    """Tests for TranscriptionOrchestrator initialization."""

    def test_stores_dependencies(self):
        router = MagicMock()
        handler = MagicMock()
        llm = MagicMock()
        tp = MagicMock()

        orch = TranscriptionOrchestrator(router, handler, llm, tp)

        assert orch.transcription_router is router
        assert orch.audio_handler is handler
        assert orch.llm_service is llm
        assert orch.text_processor is tp

    def test_optional_dependencies_default_none(self):
        orch = TranscriptionOrchestrator(MagicMock(), MagicMock())
        assert orch.llm_service is None
        assert orch.text_processor is None


# ---------------------------------------------------------------------------
# Tests: _preprocess_audio
# ---------------------------------------------------------------------------


class TestPreprocessAudio:
    """Tests for _preprocess_audio."""

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_no_preprocessing_returns_original(self, mock_settings, _mock_gs):
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False

        orch = _make_orchestrator()
        orch.audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        request = _make_request()

        processed, persistent = await orch._preprocess_audio(request)

        assert processed == Path("/tmp/test_audio.ogg")
        assert persistent is None

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_preprocessing_returns_new_path(self, mock_settings, _mock_gs):
        mock_settings.audio_convert_to_mono = True
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False

        new_path = Path("/tmp/processed.ogg")
        orch = _make_orchestrator()
        orch.audio_handler.preprocess_audio = AsyncMock(return_value=new_path)
        request = _make_request()

        processed, persistent = await orch._preprocess_audio(request)
        assert processed == new_path

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_preprocessing_failure_returns_original(self, mock_settings, _mock_gs):
        mock_settings.audio_convert_to_mono = True
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False

        orch = _make_orchestrator()
        orch.audio_handler.preprocess_audio = AsyncMock(side_effect=RuntimeError("ffmpeg failed"))
        request = _make_request()

        processed, persistent = await orch._preprocess_audio(request)
        assert processed == request.file_path

    @patch("src.services.transcription_orchestrator.save_audio_file_for_retranscription")
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_retranscription_save_enabled(self, mock_settings, mock_get_session, mock_save):
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = True

        persistent = Path("/data/persistent/abc.ogg")
        mock_save.return_value = persistent

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx
        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator()
            orch.audio_handler.preprocess_audio = AsyncMock(
                return_value=Path("/tmp/test_audio.ogg")
            )
            request = _make_request()

            processed, pers_path = await orch._preprocess_audio(request)

        assert pers_path == persistent
        mock_save.assert_called_once()
        mock_usage_repo.update.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: _run_transcription
# ---------------------------------------------------------------------------


class TestRunTranscription:
    """Tests for _run_transcription."""

    async def test_calls_router_and_stops_progress(self):
        result = _make_result()
        orch = _make_orchestrator()
        orch.transcription_router.transcribe = AsyncMock(return_value=result)

        request = _make_request()
        progress = AsyncMock()
        progress.stop = AsyncMock()

        actual = await orch._run_transcription(request, Path("/tmp/test_audio.ogg"), progress)

        assert actual is result
        orch.transcription_router.transcribe.assert_awaited_once_with(
            Path("/tmp/test_audio.ogg"), request.context
        )
        progress.stop.assert_awaited_once()
        request.status_message.edit_text.assert_awaited()


# ---------------------------------------------------------------------------
# Tests: _apply_structuring
# ---------------------------------------------------------------------------


class TestApplyStructuring:
    """Tests for _apply_structuring."""

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_saves_variants_and_returns_structured(self, mock_settings, mock_get_session):
        mock_settings.llm_model = "deepseek-chat"

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_variant_repo = MagicMock()
        mock_variant_repo.create = AsyncMock()
        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
        ):
            text_processor = MagicMock()
            text_processor.create_structured = AsyncMock(return_value="<b>Structured</b> text")
            orch = _make_orchestrator(text_processor=text_processor)

            request = _make_request()
            result = _make_result(text="Raw text")

            structured, llm_time = await orch._apply_structuring(
                request, result, show_draft=False, emoji_level=1
            )

        assert structured == "<b>Structured</b> text"
        assert llm_time >= 0
        # Original + structured variants saved (2 create calls across sessions)
        assert mock_variant_repo.create.await_count == 2

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_show_draft_sends_and_deletes_messages(self, mock_settings, mock_get_session):
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_variant_repo = MagicMock()
        mock_variant_repo.create = AsyncMock()
        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=5)

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
        ):
            text_processor = MagicMock()
            text_processor.create_structured = AsyncMock(return_value="Structured")
            orch = _make_orchestrator(text_processor=text_processor)

            request = _make_request()
            result = _make_result(text="Draft text")

            # Execute
            await orch._apply_structuring(request, result, show_draft=True, emoji_level=0)

        # Draft messages should have been populated and then deleted
        # (the _send_draft_messages creates them, then structuring deletes them)

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_no_draft_deletes_status_message(self, mock_settings, mock_get_session):
        mock_settings.llm_model = "deepseek-chat"

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_variant_repo = MagicMock()
        mock_variant_repo.create = AsyncMock()
        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
        ):
            text_processor = MagicMock()
            text_processor.create_structured = AsyncMock(return_value="Result")
            orch = _make_orchestrator(text_processor=text_processor)

            request = _make_request()
            result = _make_result()

            await orch._apply_structuring(request, result, show_draft=False, emoji_level=0)

        request.status_message.delete.assert_awaited()


# ---------------------------------------------------------------------------
# Tests: _apply_refinement
# ---------------------------------------------------------------------------


class TestApplyRefinement:
    """Tests for _apply_refinement."""

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_calls_llm_and_returns_refined(self, mock_settings, mock_get_session):
        mock_settings.llm_debug_mode = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=3)

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            llm_service = MagicMock()
            llm_service.refine_transcription = AsyncMock(return_value="Refined text")
            orch = _make_orchestrator(llm_service=llm_service)

            request = _make_request()
            result = _make_result(text="Draft text")

            refined, llm_time = await orch._apply_refinement(request, result)

        assert refined == "Refined text"
        assert llm_time >= 0
        llm_service.refine_transcription.assert_awaited_once_with("Draft text")
        mock_usage_repo.update.assert_awaited()

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_debug_mode_sends_comparison(self, mock_settings, mock_get_session):
        mock_settings.llm_debug_mode = True
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            llm_service = MagicMock()
            llm_service.refine_transcription = AsyncMock(return_value="Refined")
            orch = _make_orchestrator(llm_service=llm_service)

            request = _make_request()
            result = _make_result(text="Draft", model_name="whisper-1")

            await orch._apply_refinement(request, result)

        # Debug comparison message sent
        request.user_message.reply_text.assert_awaited()
        # Check that the debug message contains comparison keywords
        call_args = request.user_message.reply_text.await_args
        assert "Сравнение" in call_args[0][0]

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_deletes_draft_messages(self, mock_settings, mock_get_session):
        mock_settings.llm_debug_mode = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            llm_service = MagicMock()
            llm_service.refine_transcription = AsyncMock(return_value="Refined")
            orch = _make_orchestrator(llm_service=llm_service)

            request = _make_request()
            # Simulate draft messages already populated
            draft_msg = AsyncMock()
            request.draft_messages.append(draft_msg)

            result = _make_result(text="Draft")
            await orch._apply_refinement(request, result)

        draft_msg.delete.assert_awaited()


# ---------------------------------------------------------------------------
# Tests: _create_interactive_state_and_keyboard
# ---------------------------------------------------------------------------


class TestCreateInteractiveStateAndKeyboard:
    """Tests for _create_interactive_state_and_keyboard."""

    @patch("src.services.transcription_orchestrator.settings")
    async def test_interactive_disabled_returns_none(self, mock_settings):
        mock_settings.interactive_mode_enabled = False
        orch = _make_orchestrator()
        result = _make_result()

        keyboard = await orch._create_interactive_state_and_keyboard(
            usage_id=1,
            message_id=10,
            chat_id=12345,
            result=result,
            final_text="text",
        )
        assert keyboard is None

    @patch("src.services.transcription_orchestrator.create_transcription_keyboard")
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_creates_state_and_keyboard(
        self, mock_settings, mock_get_session, mock_create_kb
    ):
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = False

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_state = MagicMock()
        mock_state.id = 1
        mock_state_repo = MagicMock()
        mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
        mock_state_repo.create = AsyncMock(return_value=mock_state)

        mock_variant_repo = MagicMock()
        mock_variant_repo.get_variant = AsyncMock(return_value=None)
        mock_variant_repo.create = AsyncMock()

        mock_segment_repo = MagicMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionStateRepository",
                return_value=mock_state_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionSegmentRepository",
                return_value=mock_segment_repo,
            ),
        ):
            expected_kb = MagicMock()
            mock_create_kb.return_value = expected_kb

            orch = _make_orchestrator()
            result = _make_result()

            keyboard = await orch._create_interactive_state_and_keyboard(
                usage_id=1,
                message_id=10,
                chat_id=12345,
                result=result,
                final_text="hello",
            )

        assert keyboard is expected_kb
        mock_state_repo.create.assert_awaited_once()
        mock_variant_repo.create.assert_awaited_once()

    @patch("src.services.transcription_orchestrator.create_transcription_keyboard")
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_existing_state_reuses_it(self, mock_settings, mock_get_session, mock_create_kb):
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = False

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        existing_state = MagicMock()
        existing_state.id = 5
        mock_state_repo = MagicMock()
        mock_state_repo.get_by_usage_id = AsyncMock(return_value=existing_state)
        mock_state_repo.create = AsyncMock()

        mock_variant_repo = MagicMock()
        mock_variant_repo.get_variant = AsyncMock(return_value=MagicMock())

        mock_segment_repo = MagicMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionStateRepository",
                return_value=mock_state_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionSegmentRepository",
                return_value=mock_segment_repo,
            ),
        ):
            mock_create_kb.return_value = MagicMock()

            orch = _make_orchestrator()
            result = _make_result()

            await orch._create_interactive_state_and_keyboard(
                usage_id=1,
                message_id=10,
                chat_id=12345,
                result=result,
                final_text="text",
            )

        mock_state_repo.create.assert_not_awaited()

    @patch("src.services.transcription_orchestrator.create_transcription_keyboard")
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_segments_saved_when_conditions_met(
        self, mock_settings, mock_get_session, mock_create_kb
    ):
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = True
        mock_settings.timestamps_min_duration = 10

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_state_repo = MagicMock()
        mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
        mock_state_repo.create = AsyncMock(return_value=MagicMock(id=1))

        mock_variant_repo = MagicMock()
        mock_variant_repo.get_variant = AsyncMock(return_value=None)
        mock_variant_repo.create = AsyncMock()

        mock_segment_repo = MagicMock()
        mock_segment_repo.create_batch = AsyncMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionStateRepository",
                return_value=mock_state_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionSegmentRepository",
                return_value=mock_segment_repo,
            ),
        ):
            mock_create_kb.return_value = MagicMock()
            orch = _make_orchestrator()

            segments = [
                TranscriptionSegment(start=0.0, end=5.0, text="Hello"),
                TranscriptionSegment(start=5.0, end=10.0, text="World"),
            ]
            result = _make_result(audio_duration=30.0, segments=segments)

            await orch._create_interactive_state_and_keyboard(
                usage_id=1,
                message_id=10,
                chat_id=12345,
                result=result,
                final_text="text",
            )

        mock_segment_repo.create_batch.assert_awaited_once()

    @patch("src.services.transcription_orchestrator.create_transcription_keyboard")
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_segments_not_saved_when_timestamps_disabled(
        self, mock_settings, mock_get_session, mock_create_kb
    ):
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = False
        mock_settings.timestamps_min_duration = 10

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_state_repo = MagicMock()
        mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
        mock_state_repo.create = AsyncMock(return_value=MagicMock(id=1))

        mock_variant_repo = MagicMock()
        mock_variant_repo.get_variant = AsyncMock(return_value=None)
        mock_variant_repo.create = AsyncMock()

        mock_segment_repo = MagicMock()
        mock_segment_repo.create_batch = AsyncMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionStateRepository",
                return_value=mock_state_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionSegmentRepository",
                return_value=mock_segment_repo,
            ),
        ):
            mock_create_kb.return_value = MagicMock()
            orch = _make_orchestrator()

            segments = [TranscriptionSegment(start=0.0, end=5.0, text="Hello")]
            result = _make_result(audio_duration=30.0, segments=segments)

            await orch._create_interactive_state_and_keyboard(
                usage_id=1,
                message_id=10,
                chat_id=12345,
                result=result,
                final_text="text",
            )

        mock_segment_repo.create_batch.assert_not_awaited()

    @patch("src.services.transcription_orchestrator.create_transcription_keyboard")
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_segments_not_saved_when_duration_below_threshold(
        self, mock_settings, mock_get_session, mock_create_kb
    ):
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = True
        mock_settings.timestamps_min_duration = 60  # high threshold

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_state_repo = MagicMock()
        mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
        mock_state_repo.create = AsyncMock(return_value=MagicMock(id=1))

        mock_variant_repo = MagicMock()
        mock_variant_repo.get_variant = AsyncMock(return_value=None)
        mock_variant_repo.create = AsyncMock()

        mock_segment_repo = MagicMock()
        mock_segment_repo.create_batch = AsyncMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionStateRepository",
                return_value=mock_state_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionSegmentRepository",
                return_value=mock_segment_repo,
            ),
        ):
            mock_create_kb.return_value = MagicMock()
            orch = _make_orchestrator()

            segments = [TranscriptionSegment(start=0.0, end=5.0, text="Hi")]
            result = _make_result(audio_duration=30.0, segments=segments)

            await orch._create_interactive_state_and_keyboard(
                usage_id=1,
                message_id=10,
                chat_id=12345,
                result=result,
                final_text="text",
            )

        mock_segment_repo.create_batch.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: _send_transcription_result
# ---------------------------------------------------------------------------


class TestSendTranscriptionResult:
    """Tests for _send_transcription_result."""

    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_short_text_sends_message(self, mock_settings, mock_get_session, _mock_sanitize):
        mock_settings.file_threshold_chars = 5000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage = MagicMock(user_id=100)
        mock_usage_repo.get_by_id = AsyncMock(return_value=mock_usage)
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator()
            request = _make_request()

            msg, file_msg = await orch._send_transcription_result(
                request, "Short text", keyboard=None, usage_id=1
            )

        assert file_msg is None
        request.user_message.reply_text.assert_awaited()

    @patch("src.services.transcription_orchestrator.create_file_object")
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_long_text_sends_file(
        self, mock_settings, mock_get_session, _mock_sanitize, mock_create_file
    ):
        mock_settings.file_threshold_chars = 10  # very low threshold

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=2)

        mock_file_obj = MagicMock()
        mock_file_obj.name = "2_original.txt"
        mock_create_file.return_value = (mock_file_obj, "TXT")

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator()
            request = _make_request()

            msg, file_msg = await orch._send_transcription_result(
                request, "A" * 100, keyboard=None, usage_id=1
            )

        assert file_msg is not None
        request.user_message.reply_document.assert_awaited()

    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_keyboard_attached_to_message(
        self, mock_settings, mock_get_session, _mock_sanitize
    ):
        mock_settings.file_threshold_chars = 5000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        kb = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator()
            request = _make_request()

            await orch._send_transcription_result(request, "Text", keyboard=kb, usage_id=1)

        call_kwargs = request.user_message.reply_text.await_args
        assert (
            call_kwargs.kwargs.get("reply_markup") is kb or call_kwargs[1].get("reply_markup") is kb
        )


# ---------------------------------------------------------------------------
# Tests: _send_draft_messages
# ---------------------------------------------------------------------------


class TestSendDraftMessages:
    """Tests for _send_draft_messages."""

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_short_draft_sends_text(self, mock_settings, mock_get_session, _mock_escape):
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator()
            request = _make_request()

            await orch._send_draft_messages(request, "Short draft")

        assert len(request.draft_messages) == 1
        request.user_message.reply_text.assert_awaited()

    @patch("src.services.transcription_orchestrator.create_file_object")
    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_long_draft_sends_file(
        self, mock_settings, mock_get_session, _mock_escape, mock_create_file
    ):
        mock_settings.file_threshold_chars = 10

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        mock_file_obj = MagicMock()
        mock_file_obj.name = "1_original.txt"
        mock_create_file.return_value = (mock_file_obj, "TXT")

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator()
            request = _make_request()

            await orch._send_draft_messages(request, "A" * 100)

        # Long draft: info_msg + file_msg = 2 draft messages
        assert len(request.draft_messages) == 2
        request.user_message.reply_document.assert_awaited()


# ---------------------------------------------------------------------------
# Tests: _send_result_and_update_state
# ---------------------------------------------------------------------------


class TestSendResultAndUpdateState:
    """Tests for _send_result_and_update_state."""

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_calls_create_keyboard_and_send(self, mock_settings, mock_get_session):
        mock_settings.interactive_mode_enabled = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        with (
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.sanitize_markdown",
                side_effect=lambda x: x,
            ),
        ):
            orch = _make_orchestrator()
            request = _make_request()
            result = _make_result()

            await orch._send_result_and_update_state(request, "Final text", result)

        request.user_message.reply_text.assert_awaited()

    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_updates_state_with_message_ids(self, mock_settings, mock_get_session):
        mock_settings.interactive_mode_enabled = True
        mock_settings.enable_timestamps_option = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_state = MagicMock()
        mock_state.id = 1
        mock_state_repo = MagicMock()
        mock_state_repo.get_by_usage_id = AsyncMock(return_value=None)
        mock_state_repo.get_by_message = AsyncMock(return_value=None)
        mock_state_repo.create = AsyncMock(return_value=mock_state)
        mock_state_repo.update = AsyncMock()

        mock_variant_repo = MagicMock()
        mock_variant_repo.get_variant = AsyncMock(return_value=None)
        mock_variant_repo.create = AsyncMock()

        mock_segment_repo = MagicMock()

        mock_usage_repo = MagicMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        kb = MagicMock()

        with (
            patch(
                "src.services.transcription_orchestrator.TranscriptionStateRepository",
                return_value=mock_state_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionSegmentRepository",
                return_value=mock_segment_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.create_transcription_keyboard",
                return_value=kb,
            ),
            patch(
                "src.services.transcription_orchestrator.sanitize_markdown",
                side_effect=lambda x: x,
            ),
        ):
            orch = _make_orchestrator()
            request = _make_request()
            result = _make_result()

            # Second call to get_by_usage_id (in _send_result_and_update_state)
            # returns our state so update is called
            mock_state_repo.get_by_usage_id = AsyncMock(side_effect=[None, mock_state])
            mock_state_repo.create = AsyncMock(return_value=mock_state)

            await orch._send_result_and_update_state(
                request, "text", result, active_mode="original"
            )

        # State should have been updated with message_id
        mock_state_repo.update.assert_awaited()


# ---------------------------------------------------------------------------
# Tests: process_transcription (main pipeline)
# ---------------------------------------------------------------------------


class TestProcessTranscription:
    """Tests for process_transcription — the main orchestration method."""

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_simple_mode_pipeline(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """No structuring, no refinement -> preprocess, transcribe, send."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Hello world")
        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        # Simple strategy: not HybridStrategy, no requires_structuring
        router.strategy = MagicMock(spec=[])  # no requires_structuring attr

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator(router=router, audio_handler=audio_handler)
            request = _make_request()

            returned = await orch.process_transcription(request)

        assert returned is result
        progress_instance.start.assert_awaited_once()
        progress_instance.stop.assert_awaited_once()
        router.transcribe.assert_awaited_once()
        audio_handler.cleanup_file.assert_called()
        mock_usage_repo.update.assert_awaited()

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_structure_strategy_pipeline(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """StructureStrategy -> preprocess, transcribe, structure, send."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000
        mock_settings.llm_model = "deepseek-chat"

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        mock_variant_repo = MagicMock()
        mock_variant_repo.create = AsyncMock()

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Raw text")
        strategy = MagicMock()
        strategy.requires_structuring = MagicMock(return_value=True)
        strategy.should_show_draft = MagicMock(return_value=False)
        strategy.get_emoji_level = MagicMock(return_value=1)

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = strategy

        text_processor = MagicMock()
        text_processor.create_structured = AsyncMock(return_value="Structured text")

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with (
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
        ):
            orch = _make_orchestrator(
                router=router,
                audio_handler=audio_handler,
                text_processor=text_processor,
            )
            request = _make_request(duration_seconds=60)

            returned = await orch.process_transcription(request)

        assert returned is result
        text_processor.create_structured.assert_awaited_once()
        strategy.requires_structuring.assert_called()

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_hybrid_strategy_with_refinement(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """HybridStrategy + long audio -> preprocess, transcribe, refine, send."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_debug_mode = False

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Draft from whisper")

        from src.transcription.routing.strategies import HybridStrategy

        hybrid_strategy = MagicMock(spec=HybridStrategy)
        hybrid_strategy.requires_refinement = MagicMock(return_value=True)

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="faster-whisper")
        router.get_active_provider_model = MagicMock(return_value="small")
        router.strategy = hybrid_strategy

        llm_service = MagicMock()
        llm_service.refine_transcription = AsyncMock(return_value="Refined text")

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator(
                router=router,
                audio_handler=audio_handler,
                llm_service=llm_service,
            )
            request = _make_request(duration_seconds=120)

            returned = await orch.process_transcription(request)

        assert returned is result
        llm_service.refine_transcription.assert_awaited_once()
        hybrid_strategy.requires_refinement.assert_called_with(120)

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_structuring_failure_fallback(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """Structuring error -> fallback to original text."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000
        mock_settings.llm_model = "deepseek-chat"

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        mock_variant_repo = MagicMock()
        mock_variant_repo.create = AsyncMock(side_effect=RuntimeError("DB error"))

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Original text")

        strategy = MagicMock()
        strategy.requires_structuring = MagicMock(return_value=True)
        strategy.should_show_draft = MagicMock(return_value=False)
        strategy.get_emoji_level = MagicMock(return_value=0)

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = strategy

        text_processor = MagicMock()
        text_processor.create_structured = AsyncMock(return_value="Structured")

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with (
            patch(
                "src.services.transcription_orchestrator.UsageRepository",
                return_value=mock_usage_repo,
            ),
            patch(
                "src.services.transcription_orchestrator.TranscriptionVariantRepository",
                return_value=mock_variant_repo,
            ),
        ):
            orch = _make_orchestrator(
                router=router,
                audio_handler=audio_handler,
                text_processor=text_processor,
            )
            request = _make_request(duration_seconds=60)

            returned = await orch.process_transcription(request)

        # Should still return result (fallback path)
        assert returned is result
        audio_handler.cleanup_file.assert_called()

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_refinement_failure_fallback(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """Refinement error -> fallback with error message."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000
        mock_settings.llm_model = "deepseek-chat"
        mock_settings.llm_debug_mode = False

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Draft text")

        from src.transcription.routing.strategies import HybridStrategy

        hybrid_strategy = MagicMock(spec=HybridStrategy)
        hybrid_strategy.requires_refinement = MagicMock(return_value=True)

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="faster-whisper")
        router.get_active_provider_model = MagicMock(return_value="small")
        router.strategy = hybrid_strategy

        llm_service = MagicMock()
        llm_service.refine_transcription = AsyncMock(side_effect=RuntimeError("LLM API error"))

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator(
                router=router,
                audio_handler=audio_handler,
                llm_service=llm_service,
            )
            request = _make_request(duration_seconds=120)

            returned = await orch.process_transcription(request)

        assert returned is result
        # Status message should show error fallback
        request.status_message.edit_text.assert_awaited()

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_error_stops_progress_and_cleans_up(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """Fatal error -> progress stopped, status updated, files cleaned."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        router = MagicMock()
        router.transcribe = AsyncMock(side_effect=RuntimeError("Fatal error"))
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = MagicMock(spec=[])

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        orch = _make_orchestrator(router=router, audio_handler=audio_handler)
        request = _make_request()

        with pytest.raises(RuntimeError, match="Fatal error"):
            await orch.process_transcription(request)

        progress_instance.stop.assert_awaited()
        request.status_message.edit_text.assert_awaited()
        audio_handler.cleanup_file.assert_called()

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_cleanup_temp_files_on_success(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """After success: both original and processed files cleaned up."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = True
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Text")
        processed = Path("/tmp/processed.ogg")

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = MagicMock(spec=[])

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=processed)
        audio_handler.cleanup_file = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator(router=router, audio_handler=audio_handler)
            request = _make_request()

            await orch.process_transcription(request)

        # Both original and processed files should be cleaned up
        assert audio_handler.cleanup_file.call_count == 2
        audio_handler.cleanup_file.assert_any_call(request.file_path)
        audio_handler.cleanup_file.assert_any_call(processed)

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_disable_refinement_skips_llm(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """context.disable_refinement=True -> no LLM refinement."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(text="Direct text")

        from src.transcription.routing.strategies import HybridStrategy

        hybrid_strategy = MagicMock(spec=HybridStrategy)
        hybrid_strategy.requires_refinement = MagicMock(return_value=True)

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = hybrid_strategy

        llm_service = MagicMock()
        llm_service.refine_transcription = AsyncMock(return_value="Refined")

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator(
                router=router,
                audio_handler=audio_handler,
                llm_service=llm_service,
            )
            request = _make_request(duration_seconds=120, disable_refinement=True)

            await orch.process_transcription(request)

        # LLM should NOT have been called
        llm_service.refine_transcription.assert_not_awaited()

    @patch("src.services.transcription_orchestrator.escape_markdownv2", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.sanitize_markdown", side_effect=lambda x: x)
    @patch("src.services.transcription_orchestrator.get_session")
    @patch("src.services.transcription_orchestrator.ProgressTracker")
    @patch("src.services.transcription_orchestrator.settings")
    async def test_usage_record_updated_with_final_stats(
        self, mock_settings, MockProgress, mock_get_session, _mock_sanitize, _mock_escape
    ):
        """After success, usage record is updated with model, time, length."""
        mock_settings.progress_rtf = 0.3
        mock_settings.progress_update_interval = 5
        mock_settings.interactive_mode_enabled = False
        mock_settings.audio_convert_to_mono = False
        mock_settings.audio_speed_multiplier = 1.0
        mock_settings.enable_retranscribe = False
        mock_settings.file_threshold_chars = 10000

        mock_ctx, mock_session = _mock_session_ctx()
        mock_get_session.return_value = mock_ctx

        mock_usage_repo = MagicMock()
        mock_usage_repo.update = AsyncMock()
        mock_usage_repo.get_by_id = AsyncMock(return_value=MagicMock(user_id=100))
        mock_usage_repo.count_by_user_id = AsyncMock(return_value=1)

        progress_instance = AsyncMock()
        MockProgress.return_value = progress_instance

        result = _make_result(
            text="Some text",
            model_name="whisper-1",
            processing_time=2.5,
        )

        router = MagicMock()
        router.transcribe = AsyncMock(return_value=result)
        router.get_active_provider_name = MagicMock(return_value="openai")
        router.get_active_provider_model = MagicMock(return_value="whisper-1")
        router.strategy = MagicMock(spec=[])

        audio_handler = MagicMock()
        audio_handler.preprocess_audio = AsyncMock(return_value=Path("/tmp/test_audio.ogg"))
        audio_handler.cleanup_file = MagicMock()

        with patch(
            "src.services.transcription_orchestrator.UsageRepository",
            return_value=mock_usage_repo,
        ):
            orch = _make_orchestrator(router=router, audio_handler=audio_handler)
            request = _make_request()

            await orch.process_transcription(request)

        # Check that update was called with expected fields
        update_calls = mock_usage_repo.update.await_args_list
        # The last call should contain model_size, processing_time, etc.
        last_call = update_calls[-1]
        assert last_call.kwargs["model_size"] == "whisper-1"
        assert last_call.kwargs["processing_time_seconds"] == 2.5
