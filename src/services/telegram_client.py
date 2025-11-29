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
    Requires api_id and api_hash from my.telegram.org.
    """

    def __init__(self):
        """Initialize Telethon client with bot credentials.

        Raises:
            ValueError: If api_id or api_hash not configured
        """
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise ValueError(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set to use Client API. "
                "Obtain them from https://my.telegram.org"
            )

        self.client = TelegramClient(
            session=settings.telethon_session_name,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
        )
        self._started = False
        logger.info(
            f"TelegramClientService initialized with session: {settings.telethon_session_name}"
        )

    async def start(self) -> None:
        """Start Telethon client with bot token.

        Creates/loads session file for persistent authentication.
        Session file is named: {telethon_session_name}.session
        """
        if not self._started:
            await self.client.start(bot_token=settings.telegram_bot_token)
            self._started = True
            logger.info("Telethon client started successfully")

    async def stop(self) -> None:
        """Stop Telethon client and disconnect."""
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
            logger.info(f"Downloading large file: chat_id={chat_id}, message_id={message_id}")

            # Get message
            message: Message = await self.client.get_messages(chat_id, ids=message_id)

            if not message:
                logger.error(f"Message {message_id} not found in chat {chat_id}")
                return None

            if not message.media:
                logger.error(f"Message {message_id} has no media")
                return None

            # Download media to output directory
            logger.debug(f"Starting download to {output_dir}")
            file_path = await self.client.download_media(message=message, file=output_dir)

            if file_path:
                file_path = Path(file_path)
                file_size_mb = file_path.stat().st_size / 1024 / 1024
                logger.info(
                    f"Large file downloaded successfully: {file_path.name} ({file_size_mb:.2f} MB)"
                )
                return file_path
            else:
                logger.error("Download returned None")
                return None

        except Exception as e:
            logger.error(f"Failed to download large file: {e}", exc_info=True)
            raise RuntimeError(f"Large file download failed: {e}") from e

    async def __aenter__(self):
        """Context manager entry: start client."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: stop client."""
        await self.stop()
