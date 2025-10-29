"""Progress tracker for displaying live transcription progress."""

import asyncio
import logging
import time
from typing import Optional

from telegram import Message
from telegram.error import TelegramError, RetryAfter, TimedOut

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Tracks and displays transcription progress with live updates.

    Features:
    - Live progress bar updates every N seconds
    - Estimated time remaining based on RTF
    - Visual progress bar with emoji
    - Handles Telegram rate limits gracefully
    """

    def __init__(
        self,
        message: Message,
        duration_seconds: int,
        rtf: float = 0.3,
        update_interval: int = 5,
    ):
        """Initialize progress tracker.

        Args:
            message: Telegram message to update with progress
            duration_seconds: Audio duration in seconds
            rtf: Real-time factor (processing_time / audio_duration)
            update_interval: Seconds between progress updates
        """
        self.message = message
        self.duration_seconds = duration_seconds
        self.estimated_total_seconds = duration_seconds * rtf
        self.update_interval = update_interval
        self.start_time = time.time()
        self._task: Optional[asyncio.Task] = None
        self._stopped = False

        logger.info(
            f"ProgressTracker initialized: "
            f"duration={duration_seconds}s, estimated={self.estimated_total_seconds:.1f}s, "
            f"interval={update_interval}s"
        )

    async def start(self) -> None:
        """Start progress updates in background."""
        if self._task is not None:
            logger.warning("Progress tracker already running")
            return

        self._stopped = False
        self._task = asyncio.create_task(self._update_loop())
        logger.info("Progress tracker started")

    async def stop(self) -> None:
        """Stop progress updates gracefully."""
        if self._task is None:
            return

        self._stopped = True
        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None
        logger.info("Progress tracker stopped")

    async def _update_loop(self) -> None:
        """Background loop that updates progress every interval."""
        last_update_time = 0.0

        while not self._stopped:
            try:
                # Wait for interval
                await asyncio.sleep(self.update_interval)

                # Check if enough time passed since last update (rate limit protection)
                current_time = time.time()
                if current_time - last_update_time < self.update_interval - 0.5:
                    continue

                # Calculate progress
                elapsed = current_time - self.start_time
                progress_pct = min(int(elapsed / self.estimated_total_seconds * 100), 99)
                remaining = max(int(self.estimated_total_seconds - elapsed), 0)

                # Generate progress message
                bar = self._generate_bar(progress_pct)
                text = (
                    f"🔄 Обработка {bar} {progress_pct}%\n"
                    f"⏱️ Прошло: {int(elapsed)}с | Осталось: ~{remaining}с"
                )

                # Update message
                await self._safe_update(text)
                last_update_time = current_time

            except asyncio.CancelledError:
                logger.debug("Progress update loop cancelled")
                break
            except Exception as e:
                logger.warning(f"Error in progress update loop: {e}")
                # Continue updating despite errors

    async def _safe_update(self, text: str) -> None:
        """Safely update message with error handling.

        Args:
            text: New message text
        """
        try:
            await self.message.edit_text(text)
            logger.debug(f"Progress updated: {text[:50]}...")

        except RetryAfter as e:
            # Telegram rate limit hit
            retry_after = e.retry_after
            logger.warning(f"Rate limited, retry after {retry_after}s")
            # Convert to float (retry_after can be int or timedelta)
            sleep_duration = float(
                retry_after.total_seconds()
                if hasattr(retry_after, "total_seconds")
                else retry_after
            )
            await asyncio.sleep(sleep_duration)

        except TimedOut:
            # Network timeout
            logger.warning("Message update timed out")

        except TelegramError as e:
            # Other Telegram errors (message not found, etc)
            if "message is not modified" in str(e).lower():
                # Message content unchanged, ignore
                pass
            elif "message to edit not found" in str(e).lower():
                # Message was deleted, stop tracker
                logger.warning("Message deleted, stopping tracker")
                self._stopped = True
            else:
                logger.warning(f"Telegram error updating message: {e}")

        except Exception as e:
            logger.error(f"Unexpected error updating progress: {e}", exc_info=True)

    def _generate_bar(self, percent: int) -> str:
        """Generate visual progress bar.

        Args:
            percent: Progress percentage (0-100)

        Returns:
            Progress bar string like [████████░░░░░░░░░░]
        """
        # 20 blocks total (5% each)
        filled = min(int(percent / 5), 20)
        empty = 20 - filled
        return f"[{'█' * filled}{'░' * empty}]"

    def get_elapsed_time(self) -> float:
        """Get elapsed time since start.

        Returns:
            Elapsed seconds
        """
        return time.time() - self.start_time

    def get_progress_percent(self) -> int:
        """Get current progress percentage.

        Returns:
            Progress percentage (0-100)
        """
        elapsed = self.get_elapsed_time()
        return min(int(elapsed / self.estimated_total_seconds * 100), 99)
