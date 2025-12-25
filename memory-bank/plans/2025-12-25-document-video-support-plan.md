# Plan: Document & Video Support with Audio Extraction

**Date**: 2025-12-25
**Status**: Approved, awaiting implementation
**Selected Option**: Option 2 (Comprehensive)

## Problem Statement

Бот не обрабатывает файлы, отправленные как документы (например, `.aac`), а также видео файлы. Telegram различает:
- `message.voice` — голосовые сообщения (записанные через кнопку микрофона)
- `message.audio` — аудио файлы (музыка с метаданными)
- `message.document` — любые файлы, включая аудио/видео
- `message.video` — видео файлы

Текущие обработчики покрывают только voice и audio.

## Solution Overview

Добавить обработчики для:
1. **Document** с audio MIME-типами (`audio/*`)
2. **Video** файлов (`video/*`) — с извлечением аудиодорожки

## Implementation Tasks

### Task 1: Extend supported formats in AudioHandler

**File**: `src/transcription/audio_handler.py`

**Changes**:
```python
# Line ~35: Extend supported_formats
self.supported_formats = {
    # Existing
    ".ogg", ".oga", ".mp3", ".wav", ".m4a", ".opus",
    # New audio formats
    ".aac", ".flac", ".wma", ".amr", ".webm", ".3gp",
    # Video formats (for audio extraction)
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
}
```

### Task 2: Add audio extraction method

**File**: `src/transcription/audio_handler.py`

**New method** (add after `_convert_to_wav`):
```python
def extract_audio_track(self, input_path: Path) -> Path:
    """
    Extract audio track from video/media file.

    Converts to mono Opus format optimized for Whisper.

    Args:
        input_path: Input video/media file

    Returns:
        Path to extracted audio file (OGG format)

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
        ValueError: If file has no audio stream
    """
    # Check if file has audio stream
    if not self._has_audio_stream(input_path):
        raise ValueError(f"File has no audio stream: {input_path.name}")

    original_size = input_path.stat().st_size
    original_size_mb = original_size / (1024 * 1024)

    output_path = input_path.parent / f"{input_path.stem}_extracted.ogg"

    logger.info(
        f"Extracting audio from {input_path.name} ({original_size_mb:.2f}MB)"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",  # Overwrite
            "-i", str(input_path),
            "-vn",  # No video
            "-ac", "1",  # Mono
            "-ar", str(settings.audio_target_sample_rate),  # 16kHz
            "-acodec", "libopus",
            "-b:a", "32k",  # 32 kbps
            "-vbr", "on",
            "-f", "ogg",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    converted_size = output_path.stat().st_size
    converted_size_mb = converted_size / (1024 * 1024)

    logger.info(
        f"Audio extraction complete: {original_size_mb:.2f}MB → {converted_size_mb:.2f}MB"
    )

    return output_path


def _has_audio_stream(self, file_path: Path) -> bool:
    """
    Check if file contains an audio stream.

    Args:
        file_path: Path to media file

    Returns:
        True if file has audio stream, False otherwise
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return "audio" in result.stdout
    except subprocess.CalledProcessError:
        return False


def get_audio_duration_ffprobe(self, file_path: Path) -> Optional[float]:
    """
    Get audio duration using ffprobe.

    Args:
        file_path: Path to audio/video file

    Returns:
        Duration in seconds or None if unavailable
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None
```

### Task 3: Add MIME type configuration

**File**: `src/config.py`

**Add after line ~90** (after existing format config):
```python
# Supported MIME types for document/video processing
SUPPORTED_AUDIO_MIMES: set[str] = {
    "audio/aac",
    "audio/mp4",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/opus",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
    "audio/x-m4a",
    "audio/m4a",
    "audio/amr",
    "audio/x-ms-wma",
    "audio/webm",
    "audio/3gpp",
}

SUPPORTED_VIDEO_MIMES: set[str] = {
    "video/mp4",
    "video/quicktime",  # .mov
    "video/x-msvideo",  # .avi
    "video/x-matroska",  # .mkv
    "video/webm",
    "video/3gpp",
    "video/mpeg",
}
```

### Task 4: Create document_message_handler

**File**: `src/bot/handlers.py`

**Add new method** (after `audio_message_handler`, around line ~1000):

```python
async def document_message_handler(
    self, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle document messages with audio MIME types.

    Processes documents that contain audio (e.g., .aac, .flac files
    sent as documents rather than audio messages).

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    from src.config import SUPPORTED_AUDIO_MIMES

    user = update.effective_user
    if not user or not update.message:
        return

    document = update.message.document
    if not document:
        return

    # Check MIME type
    mime_type = document.mime_type or ""
    if mime_type not in SUPPORTED_AUDIO_MIMES:
        # Not an audio document, ignore silently
        logger.debug(
            f"Document ignored: unsupported MIME type {mime_type}"
        )
        return

    logger.info(
        f"Processing audio document: user={user.id}, "
        f"file={document.file_name}, mime={mime_type}, "
        f"size={document.file_size}"
    )

    # Validate file size (same logic as audio_handler)
    if document.file_size:
        if settings.telethon_enabled and self.telegram_client:
            max_size = 2 * 1024 * 1024 * 1024  # 2 GB
        else:
            max_size = settings.max_file_size_bytes  # 20 MB

        if document.file_size > max_size:
            max_size_mb = max_size / 1024 / 1024
            file_size_mb = document.file_size / 1024 / 1024
            await update.message.reply_text(
                f"⚠️ Файл слишком большой.\n\n"
                f"Максимум: {max_size_mb:.0f} МБ\n"
                f"Ваш файл: {file_size_mb:.1f} МБ"
            )
            return

    # Check queue capacity
    queue_depth = self.queue_manager.get_queue_depth()
    if queue_depth >= settings.max_queue_size:
        await update.message.reply_text(
            "⚠️ Очередь переполнена. Попробуйте позже."
        )
        return

    # Send initial status
    status_msg = await update.message.reply_text("📥 Загружаю аудио файл...")

    try:
        # Download file
        if document.file_size and document.file_size > settings.max_file_size_bytes:
            if self.telegram_client and settings.telethon_enabled:
                file_path = await self.telegram_client.download_large_file(
                    message_id=update.message.message_id,
                    chat_id=update.message.chat_id,
                    output_dir=self.audio_handler.temp_dir,
                )
            else:
                await status_msg.edit_text("⚠️ Файл слишком большой.")
                return
        else:
            telegram_file = await context.bot.get_file(document.file_id)
            file_path = await self.audio_handler.download_voice_message(
                telegram_file, document.file_id
            )

        # Get duration via ffprobe (documents don't have duration metadata)
        duration_seconds = self.audio_handler.get_audio_duration_ffprobe(file_path)
        if duration_seconds is None:
            duration_seconds = 0  # Will be determined after transcription

        # Validate duration
        if duration_seconds > settings.max_voice_duration_seconds:
            await status_msg.edit_text(
                f"⚠️ Максимальная длительность: "
                f"{settings.max_voice_duration_seconds // 60} мин\n\n"
                f"Ваш файл: {int(duration_seconds) // 60} мин "
                f"{int(duration_seconds) % 60} сек"
            )
            self.audio_handler.cleanup_file(file_path)
            return

        # Create DB records and enqueue (same as audio_message_handler)
        # ... [copy the enqueue logic from audio_message_handler]

    except Exception as e:
        logger.error(f"Document processing error: {e}")
        await status_msg.edit_text(
            "❌ Ошибка обработки файла. Попробуйте другой формат."
        )
```

### Task 5: Create video_message_handler

**File**: `src/bot/handlers.py`

**Add new method** (after `document_message_handler`):

```python
async def video_message_handler(
    self, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle video messages by extracting audio track.

    Extracts audio from video files for transcription.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user = update.effective_user
    if not user or not update.message:
        return

    video = update.message.video
    if not video:
        return

    logger.info(
        f"Processing video: user={user.id}, "
        f"file={video.file_name}, duration={video.duration}s, "
        f"size={video.file_size}"
    )

    # Validate duration
    duration_seconds = 0
    if video.duration:
        if isinstance(video.duration, timedelta):
            duration_seconds = int(video.duration.total_seconds())
        else:
            duration_seconds = int(video.duration)

    if duration_seconds > settings.max_voice_duration_seconds:
        await update.message.reply_text(
            f"⚠️ Видео слишком длинное.\n\n"
            f"Максимум: {settings.max_voice_duration_seconds // 60} мин\n"
            f"Ваше видео: {duration_seconds // 60} мин {duration_seconds % 60} сек"
        )
        return

    # Validate file size
    if video.file_size:
        if settings.telethon_enabled and self.telegram_client:
            max_size = 2 * 1024 * 1024 * 1024  # 2 GB
        else:
            max_size = settings.max_file_size_bytes

        if video.file_size > max_size:
            max_size_mb = max_size / 1024 / 1024
            file_size_mb = video.file_size / 1024 / 1024
            await update.message.reply_text(
                f"⚠️ Видео слишком большое.\n\n"
                f"Максимум: {max_size_mb:.0f} МБ\n"
                f"Ваше видео: {file_size_mb:.1f} МБ"
            )
            return

    # Check queue
    queue_depth = self.queue_manager.get_queue_depth()
    if queue_depth >= settings.max_queue_size:
        await update.message.reply_text(
            "⚠️ Очередь переполнена. Попробуйте позже."
        )
        return

    status_msg = await update.message.reply_text("📥 Загружаю видео...")

    try:
        # Download video
        if video.file_size and video.file_size > settings.max_file_size_bytes:
            if self.telegram_client and settings.telethon_enabled:
                video_path = await self.telegram_client.download_large_file(
                    message_id=update.message.message_id,
                    chat_id=update.message.chat_id,
                    output_dir=self.audio_handler.temp_dir,
                )
            else:
                await status_msg.edit_text("⚠️ Видео слишком большое.")
                return
        else:
            telegram_file = await context.bot.get_file(video.file_id)
            video_path = await self.audio_handler.download_voice_message(
                telegram_file, video.file_id
            )

        # Extract audio track
        await status_msg.edit_text("🎵 Извлекаю аудиодорожку...")

        try:
            file_path = self.audio_handler.extract_audio_track(video_path)
        except ValueError as e:
            await status_msg.edit_text(
                "❌ Видео не содержит аудиодорожки."
            )
            self.audio_handler.cleanup_file(video_path)
            return

        # Cleanup original video file
        self.audio_handler.cleanup_file(video_path)

        # Create DB records and enqueue (same as audio_message_handler)
        # ... [copy the enqueue logic from audio_message_handler]

    except Exception as e:
        logger.error(f"Video processing error: {e}")
        await status_msg.edit_text(
            "❌ Ошибка обработки видео. Попробуйте другой формат."
        )
```

### Task 6: Register new handlers in main.py

**File**: `src/main.py`

**Add after line 195** (after existing audio handler):

```python
# Document handler (audio files sent as documents)
application.add_handler(
    MessageHandler(filters.DOCUMENT, bot_handlers.document_message_handler)
)

# Video handler (extract audio from video)
application.add_handler(
    MessageHandler(filters.VIDEO, bot_handlers.video_message_handler)
)
```

### Task 7: Add unit tests

**File**: `tests/unit/test_audio_extraction.py` (new file)

```python
"""Tests for audio extraction from video files."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.transcription.audio_handler import AudioHandler


class TestAudioExtraction:
    """Test suite for audio extraction functionality."""

    def test_has_audio_stream_with_audio(self, audio_handler):
        """Test detection of audio stream in file with audio."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="audio\n", returncode=0
            )
            result = audio_handler._has_audio_stream(Path("test.mp4"))
            assert result is True

    def test_has_audio_stream_without_audio(self, audio_handler):
        """Test detection when file has no audio stream."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", returncode=0
            )
            result = audio_handler._has_audio_stream(Path("test.mp4"))
            assert result is False

    def test_extract_audio_track_success(self, audio_handler, tmp_path):
        """Test successful audio extraction."""
        input_file = tmp_path / "test.mp4"
        input_file.write_bytes(b"fake video data")

        with patch.object(audio_handler, "_has_audio_stream", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                # Create expected output file
                output_file = tmp_path / "test_extracted.ogg"
                output_file.write_bytes(b"fake audio")

                result = audio_handler.extract_audio_track(input_file)
                assert result.suffix == ".ogg"

    def test_extract_audio_track_no_audio(self, audio_handler, tmp_path):
        """Test extraction fails when no audio stream."""
        input_file = tmp_path / "test.mp4"
        input_file.write_bytes(b"fake video data")

        with patch.object(audio_handler, "_has_audio_stream", return_value=False):
            with pytest.raises(ValueError, match="no audio stream"):
                audio_handler.extract_audio_track(input_file)
```

## File Changes Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `src/transcription/audio_handler.py` | Modify | +80 (new methods) |
| `src/config.py` | Modify | +25 (MIME types) |
| `src/bot/handlers.py` | Modify | +200 (2 new handlers) |
| `src/main.py` | Modify | +8 (handler registration) |
| `tests/unit/test_audio_extraction.py` | Create | +60 (new tests) |

**Total**: ~370 new lines of code

## Testing Plan

1. **Unit Tests**:
   - `_has_audio_stream()` — with/without audio
   - `extract_audio_track()` — success/failure cases
   - `get_audio_duration_ffprobe()` — valid/invalid files

2. **Integration Tests**:
   - Send `.aac` file as document → должен обработаться
   - Send `.mp4` video → должен извлечь аудио
   - Send video without audio → должен сообщить об ошибке
   - Send unsupported MIME type → должен проигнорировать

3. **Manual Tests**:
   - Переслать .aac файл боту
   - Отправить видео из галереи
   - Отправить видео-кружок
   - Проверить большие файлы (>20MB) через Telethon

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| ffprobe не установлен | Проверка при старте бота + graceful error |
| Большие видео файлы | Лимит размера + Telethon для >20MB |
| Видео без аудио | Проверка `_has_audio_stream()` до обработки |
| Corrupted файлы | Try/except с понятным сообщением |
| Неверный MIME-тип | Fallback на проверку расширения |

## Success Criteria

- [ ] `.aac` файлы обрабатываются корректно
- [ ] Видео файлы конвертируются в аудио
- [ ] Видео без звука получают понятное сообщение
- [ ] Все существующие тесты проходят
- [ ] Новые тесты покрывают функционал
- [ ] CI pipeline проходит

## Implementation Command

После утверждения запустить:
```
/workflow:execute
```
