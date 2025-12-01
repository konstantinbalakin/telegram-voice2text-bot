# Implementation Plan: Large File Support via Telethon Client API

**Date**: 2025-11-30
**Status**: In Progress
**Estimated Time**: 2-3 days
**Risk Level**: Medium

## Problem Statement

Current bot implementation uses Telegram Bot API which has a hard limit of 20 MB for file downloads via `getFile()` method. Users cannot process audio files larger than 20 MB.

## Solution Overview

Implement hybrid download strategy:
- **Files ≤20 MB**: Continue using Bot API (existing flow)
- **Files >20 MB**: Use Telethon Client API (supports up to 2 GB)

### Why Telethon over Pyrogram?

- **Active maintenance**: Telethon 1.42.0 (November 2025) vs Pyrogram 2.0.106 (April 2023, no updates)
- **Stability**: More mature library with proven track record
- **Community support**: Larger community, better documentation

## Technical Architecture

### New Component: TelegramClientService

```
┌─────────────────────────────────────────────────────────┐
│                    BotHandlers                          │
│                                                         │
│  ┌──────────────┐                                      │
│  │ Check Size   │                                      │
│  └──────┬───────┘                                      │
│         │                                              │
│    ┌────▼────┐                                        │
│    │ ≤20 MB? │                                        │
│    └────┬────┘                                        │
│         │                                              │
│    ┌────▼──────────┬──────────────┐                  │
│    │               │              │                  │
│  ┌─▼──┐         ┌──▼──┐          │                  │
│  │YES │         │ NO  │          │                  │
│  └─┬──┘         └──┬──┘          │                  │
│    │               │              │                  │
│  ┌─▼────────┐   ┌──▼──────────┐  │                  │
│  │ Bot API  │   │ Client API  │  │                  │
│  │ get_file │   │ Telethon    │  │                  │
│  └──────────┘   └─────────────┘  │                  │
└─────────────────────────────────────────────────────────┘
```

## Implementation Steps

### 1. Dependencies (pyproject.toml)

Add Telethon to project dependencies:

```toml
[tool.poetry.dependencies]
telethon = "^1.42.0"
cryptg = {version = "^0.4.0", optional = true}  # Performance boost

[tool.poetry.extras]
telethon-speedup = ["cryptg"]
```

### 2. Configuration (src/config.py)

Add new settings fields:

```python
# Telethon Client API Configuration (for files >20 MB)
telegram_api_id: int | None = Field(
    default=None,
    description="Telegram API ID from my.telegram.org"
)
telegram_api_hash: str | None = Field(
    default=None,
    description="Telegram API hash from my.telegram.org"
)
telethon_session_name: str = Field(
    default="bot_client",
    description="Telethon session file name"
)
telethon_enabled: bool = Field(
    default=False,
    description="Enable Telethon Client API for large files"
)
```

### 3. TelegramClientService (src/services/telegram_client.py)

New service for Client API operations:

```python
"""Telegram Client API service for downloading large files."""

import logging
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.tl.types import Message

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramClientService:
    """Service for downloading files via Telegram Client API (MTProto).

    Supports files up to 2 GB (Telegram limit), unlike Bot API's 20 MB limit.
    """

    def __init__(self):
        """Initialize Telethon client with bot credentials."""
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise ValueError(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set to use Client API"
            )

        self.client = TelegramClient(
            session=settings.telethon_session_name,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash
        )
        self._started = False
        logger.info(
            f"TelegramClientService initialized with session: {settings.telethon_session_name}"
        )

    async def start(self) -> None:
        """Start Telethon client with bot token."""
        if not self._started:
            await self.client.start(bot_token=settings.telegram_bot_token)
            self._started = True
            logger.info("Telethon client started")

    async def stop(self) -> None:
        """Stop Telethon client."""
        if self._started:
            await self.client.disconnect()
            self._started = False
            logger.info("Telethon client stopped")

    async def download_large_file(
        self,
        message_id: int,
        chat_id: int,
        output_dir: Path,
    ) -> Optional[Path]:
        """Download file from message via Client API.

        Args:
            message_id: Telegram message ID containing the file
            chat_id: Chat ID where message was sent
            output_dir: Directory to save downloaded file

        Returns:
            Path to downloaded file, or None if download failed

        Raises:
            RuntimeError: If client not started or download fails
        """
        if not self._started:
            raise RuntimeError("Client not started. Call start() first.")

        try:
            logger.info(
                f"Downloading large file: chat_id={chat_id}, message_id={message_id}"
            )

            # Get message
            message: Message = await self.client.get_messages(chat_id, ids=message_id)

            if not message or not message.media:
                logger.error(f"Message {message_id} has no media")
                return None

            # Download media to output directory
            file_path = await self.client.download_media(
                message=message,
                file=output_dir
            )

            if file_path:
                file_path = Path(file_path)
                logger.info(
                    f"Large file downloaded successfully: {file_path.name} "
                    f"({file_path.stat().st_size / 1024 / 1024:.2f} MB)"
                )
                return file_path
            else:
                logger.error("Download returned None")
                return None

        except Exception as e:
            logger.error(f"Failed to download large file: {e}", exc_info=True)
            raise RuntimeError(f"Large file download failed: {e}") from e
```

### 4. Handler Updates (src/bot/handlers.py)

Modify `voice_message_handler` and `audio_message_handler`:

```python
# Add to __init__
def __init__(
    self,
    whisper_service: TranscriptionRouter,
    audio_handler: AudioHandler,
    queue_manager: QueueManager,
    llm_service: Optional[LLMService] = None,
    telegram_client: Optional[TelegramClientService] = None,  # NEW
):
    # ... existing code ...
    self.telegram_client = telegram_client  # NEW

# Update download logic in voice_message_handler (around line 390)
# Replace:
#   voice_file = await context.bot.get_file(voice.file_id)
#   file_path = await self.audio_handler.download_voice_message(voice_file, voice.file_id)

# With:
if voice.file_size and voice.file_size > settings.max_file_size_bytes:
    # Large file: use Client API if available
    if self.telegram_client and settings.telethon_enabled:
        logger.info(
            f"File size {voice.file_size} bytes exceeds Bot API limit, "
            "using Client API"
        )
        file_path = await self.telegram_client.download_large_file(
            message_id=update.message.message_id,
            chat_id=update.message.chat_id,
            output_dir=self.audio_handler.temp_dir
        )
    else:
        # Client API not available, reject
        max_size_mb = settings.max_file_size_bytes / 1024 / 1024
        file_size_mb = voice.file_size / 1024 / 1024
        await update.message.reply_text(
            "⚠️ Файл слишком большой для обработки.\n\n"
            f"Максимальный размер: {max_size_mb:.0f} МБ\n"
            f"Размер вашего файла: {file_size_mb:.1f} МБ\n\n"
            "Пожалуйста, отправьте более короткое голосовое сообщение."
        )
        logger.warning(
            f"User {user.id} sent large file but Client API unavailable"
        )
        return
else:
    # Normal file: use Bot API
    voice_file = await context.bot.get_file(voice.file_id)
    file_path = await self.audio_handler.download_voice_message(
        voice_file, voice.file_id
    )
```

### 5. Bot Initialization (src/bot/bot.py)

Update bot initialization to include Telethon client:

```python
# Initialize Telethon client if enabled
telegram_client = None
if settings.telethon_enabled:
    try:
        telegram_client = TelegramClientService()
        await telegram_client.start()
        logger.info("Telethon Client API enabled for large files")
    except Exception as e:
        logger.warning(f"Failed to initialize Telethon client: {e}")
        logger.warning("Large file support disabled")

# Pass to handlers
handlers = BotHandlers(
    whisper_service=transcription_router,
    audio_handler=audio_handler,
    queue_manager=queue_manager,
    llm_service=llm_service,
    telegram_client=telegram_client,  # NEW
)
```

### 6. Environment Configuration

Update `.env.example`:

```bash
# Telegram Client API (для файлов >20 МБ)
# Получите credentials на https://my.telegram.org
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELETHON_SESSION_NAME=bot_client
TELETHON_ENABLED=true

# Максимальный размер файла (2 ГБ при использовании Client API)
MAX_FILE_SIZE_BYTES=2147483648
```

### 7. Git Configuration

Update `.gitignore`:

```
# Telethon session files
*.session
*.session-journal
```

### 8. Docker Configuration

Update `docker-compose.yml` to persist session:

```yaml
services:
  bot:
    volumes:
      - ./data:/app/data
      - ./bot_client.session:/app/bot_client.session  # Persist Telethon session
```

## Testing Strategy

### Unit Tests

1. **TelegramClientService**:
   - Mock Telethon client
   - Test successful download
   - Test error handling
   - Test client start/stop

2. **Handler Logic**:
   - Test size threshold detection
   - Test fallback to Bot API
   - Test fallback when Client API unavailable

### Integration Tests

1. **Small file (≤20 MB)**: Verify Bot API is used
2. **Large file (>20 MB)**: Verify Client API is used
3. **24 MB test file**: Real-world test case
4. **Error scenarios**: Client API unavailable, network errors

## Deployment Checklist

- [ ] Obtain `api_id` and `api_hash` from my.telegram.org
- [ ] Add to production `.env` file
- [ ] Test with 24 MB file on staging
- [ ] Verify session file is created
- [ ] Test bot restart (session persistence)
- [ ] Monitor logs for errors
- [ ] Update user documentation

## Risks & Mitigation

### Risk 1: Session File Security
**Mitigation**:
- Store in `.gitignore`
- Restrict file permissions on VPS
- Document backup procedures

### Risk 2: Rate Limiting
**Mitigation**:
- Telethon handles automatically
- Monitor logs for FloodWait errors
- Add retry logic if needed

### Risk 3: Concurrent Downloads
**Mitigation**:
- Each download is independent
- Queue manager prevents overload
- Test with multiple simultaneous large files

### Risk 4: Client API Unavailable
**Mitigation**:
- Graceful fallback to error message
- Clear user feedback
- Log for monitoring

## Success Criteria

- ✅ 24 MB file downloads successfully
- ✅ Bot API still used for files ≤20 MB
- ✅ Session persists across restarts
- ✅ Clear error messages when Client API unavailable
- ✅ No regression in existing functionality
- ✅ All tests passing

## Rollback Plan

If issues arise:
1. Set `TELETHON_ENABLED=false` in `.env`
2. Restart bot
3. Falls back to 20 MB limit with existing error messages
4. No data loss or corruption

## Documentation Updates

- [ ] `docs/getting-started/installation.md` - Add Telethon setup
- [ ] `docs/getting-started/configuration.md` - Document new env vars
- [ ] `docs/development/architecture.md` - Document hybrid download strategy
- [ ] `README.md` - Update features list

## Future Enhancements

- Progressive download with progress updates for very large files
- Streaming transcription for files >100 MB
- Automatic chunking for files >500 MB
- Metrics tracking (Bot API vs Client API usage)
