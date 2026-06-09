"""Unit tests for TelegramClientService auto-reconnect logic."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.telegram_client import TelegramClientService


@pytest.fixture
def mock_settings():
    """Patch settings to provide Telethon config."""
    with patch("src.services.telegram_client.settings") as mock:
        mock.telegram_api_id = 12345
        mock.telegram_api_hash = "test_hash"
        mock.telethon_session_name = "test_session"
        mock.telegram_bot_token = "test_token"
        yield mock


@pytest.fixture
def service(mock_settings):
    """Create TelegramClientService with mocked TelegramClient."""
    with patch("src.services.telegram_client.TelegramClient") as MockClient:
        mock_client = MagicMock()
        mock_client.is_connected = MagicMock(return_value=True)
        mock_client.start = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.get_messages = AsyncMock()
        mock_client.download_media = AsyncMock()
        MockClient.return_value = mock_client
        svc = TelegramClientService()
        return svc


class TestEnsureConnected:
    """Tests for _ensure_connected auto-reconnect logic."""

    async def test_raises_when_not_started(self, service):
        """Should raise RuntimeError if service was never started."""
        service._started = False
        with pytest.raises(RuntimeError, match="Client not started"):
            await service._ensure_connected()

    async def test_noop_when_connected(self, service):
        """Should do nothing when already connected."""
        service._started = True
        service.client.is_connected.return_value = True
        await service._ensure_connected()
        service.client.connect.assert_not_called()

    async def test_reconnects_when_disconnected(self, service):
        """Should call client.connect() when is_connected() returns False."""
        service._started = True
        service.client.is_connected.return_value = False
        await service._ensure_connected()
        service.client.connect.assert_awaited_once()

    async def test_sets_started_false_on_reconnect_failure(self, service):
        """Should reset _started flag if reconnection fails."""
        service._started = True
        service.client.is_connected.return_value = False
        service.client.connect.side_effect = ConnectionError("Network unreachable")
        with pytest.raises(ConnectionError):
            await service._ensure_connected()
        assert service._started is False


class TestDownloadLargeFileReconnect:
    """Tests for download_large_file triggering reconnect when needed."""

    async def test_download_triggers_reconnect_when_disconnected(self, service):
        """download_large_file should auto-reconnect before downloading."""
        service._started = True
        service.client.is_connected.return_value = False

        # After reconnect, simulate connected state
        async def fake_connect():
            service.client.is_connected.return_value = True

        service.client.connect.side_effect = fake_connect

        # Mock get_messages to return a message with media
        mock_message = MagicMock()
        mock_message.media = True
        service.client.get_messages.return_value = mock_message
        service.client.download_media.return_value = "/tmp/test_file.mp3"

        with patch("src.services.telegram_client.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.stat.return_value.st_size = 1024
            MockPath.return_value = mock_path
            MockPath.side_effect = lambda x: mock_path if x == "/tmp/test_file.mp3" else Path(x)

            result = await service.download_large_file(
                message_id=1, chat_id=123, output_dir=Path("/tmp")
            )

        service.client.connect.assert_awaited_once()
        assert result is not None

    async def test_download_fails_gracefully_on_reconnect_error(self, service):
        """download_large_file should raise ConnectionError if reconnect fails."""
        service._started = True
        service.client.is_connected.return_value = False
        service.client.connect.side_effect = ConnectionError("Cannot reconnect")

        with pytest.raises(ConnectionError, match="Cannot reconnect"):
            await service.download_large_file(message_id=1, chat_id=123, output_dir=Path("/tmp"))
