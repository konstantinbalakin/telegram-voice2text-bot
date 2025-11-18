"""Queue manager for handling transcription requests with concurrency control."""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Awaitable

from telegram import Message

from src.transcription.models import TranscriptionContext, TranscriptionResult

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionRequest:
    """Request for transcription processing."""

    id: str
    user_id: int
    file_path: Path
    duration_seconds: int
    context: TranscriptionContext
    status_message: Message
    user_message: Message  # Original user voice message (for replies)
    usage_id: int  # Database usage record ID for updates
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())

    def __post_init__(self) -> None:
        """Ensure ID is set."""
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class TranscriptionResponse:
    """Response from transcription processing."""

    request_id: str
    result: Optional[TranscriptionResult]
    error: Optional[str]
    processing_time: float = 0.0


class QueueManager:
    """Manages transcription queue with concurrency control.

    Features:
    - FIFO queue for transcription requests
    - Semaphore-based concurrency limiting
    - Non-blocking enqueue operation
    - Background worker for processing
    - Request tracking and result storage
    """

    def __init__(
        self,
        max_queue_size: int = 50,
        max_concurrent: int = 1,
    ):
        """Initialize queue manager.

        Args:
            max_queue_size: Maximum number of requests in queue
            max_concurrent: Maximum number of concurrent transcriptions
        """
        self._queue: asyncio.Queue[TranscriptionRequest] = asyncio.Queue(maxsize=max_queue_size)
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self._results: dict[str, TranscriptionResponse] = {}
        self._processing: set[str] = set()
        self._worker_task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable] = None
        self._max_queue_size = max_queue_size
        self._max_concurrent = max_concurrent
        self._total_pending: int = 0  # Total requests pending (in queue + being processed)

        # For tracking queue items and their durations
        self._pending_requests: list[TranscriptionRequest] = []
        self._processing_requests: list[TranscriptionRequest] = []  # Requests currently being processed
        self._lock: asyncio.Lock = asyncio.Lock()
        self._on_queue_changed: Optional[Callable[[], Awaitable[None]]] = None

        logger.info(
            f"QueueManager initialized: max_queue={max_queue_size}, max_concurrent={max_concurrent}"
        )

    async def start_worker(self, callback: Callable) -> None:
        """Start background worker to process queue.

        Args:
            callback: Async function to call for each request
                      Should accept TranscriptionRequest and return TranscriptionResult
        """
        if self._worker_task is not None:
            logger.warning("Worker already running")
            return

        self._callback = callback
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Queue worker started")

    async def stop_worker(self) -> None:
        """Stop background worker gracefully."""
        if self._worker_task is None:
            return

        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass

        self._worker_task = None
        logger.info("Queue worker stopped")

    async def enqueue(self, request: TranscriptionRequest) -> int:
        """Add request to queue.

        Args:
            request: Transcription request to enqueue

        Returns:
            Position in queue (1-based)

        Raises:
            asyncio.QueueFull: If queue is at capacity
        """
        try:
            async with self._lock:
                # Increment counter BEFORE put() to get correct position
                # This is atomic within the same coroutine
                self._total_pending += 1
                position = self._total_pending
                self._pending_requests.append(request)
                await self._queue.put(request)
            logger.info(f"Request {request.id} enqueued at position {position}")
            return position
        except asyncio.QueueFull:
            # Rollback counter on failure
            async with self._lock:
                self._total_pending -= 1
                # Remove from pending if it was added
                if request in self._pending_requests:
                    self._pending_requests.remove(request)
            logger.warning(f"Queue full, rejecting request {request.id}")
            raise

    def get_queue_depth(self) -> int:
        """Get current number of requests in queue.

        Returns:
            Number of pending requests
        """
        return self._queue.qsize()

    def get_processing_count(self) -> int:
        """Get number of requests currently processing.

        Returns:
            Number of active transcriptions
        """
        return len(self._processing)

    def is_processing(self, request_id: str) -> bool:
        """Check if request is currently being processed.

        Args:
            request_id: Request ID to check

        Returns:
            True if request is processing
        """
        return request_id in self._processing

    def get_result(self, request_id: str) -> Optional[TranscriptionResponse]:
        """Get result for completed request.

        Args:
            request_id: Request ID to get result for

        Returns:
            TranscriptionResponse if available, None otherwise
        """
        return self._results.get(request_id)

    async def wait_for_result(
        self, request_id: str, timeout: float = 300.0, poll_interval: float = 0.5
    ) -> TranscriptionResponse:
        """Wait for transcription result (non-blocking).

        Args:
            request_id: Request ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Polling interval in seconds

        Returns:
            TranscriptionResponse when available

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if result available
            if request_id in self._results:
                result = self._results.pop(request_id)
                logger.info(f"Result retrieved for request {request_id}")
                return result

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.error(f"Timeout waiting for result {request_id}")
                raise asyncio.TimeoutError(f"Request {request_id} timed out after {timeout}s")

            # Wait before next check
            await asyncio.sleep(poll_interval)

    async def _process_queue(self) -> None:
        """Background worker that processes queue with concurrency control."""
        logger.info("Queue worker processing loop started")

        while True:
            try:
                # Get next request from queue (blocks until available)
                request = await self._queue.get()

                # Process with concurrency limit
                asyncio.create_task(self._process_request(request))

            except asyncio.CancelledError:
                logger.info("Queue worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in queue worker: {e}", exc_info=True)
                # Continue processing other requests

    async def _process_request(self, request: TranscriptionRequest) -> None:
        """Process single request with semaphore control.

        Args:
            request: Request to process
        """
        request_id = request.id

        # Wait for semaphore (concurrency limit)
        async with self._semaphore:
            self._processing.add(request_id)
            start_time = asyncio.get_event_loop().time()

            # Move from pending to processing when processing starts
            async with self._lock:
                if request in self._pending_requests:
                    self._pending_requests.remove(request)
                self._processing_requests.append(request)

            # Notify about queue change (for updating other users' messages)
            if self._on_queue_changed:
                try:
                    await self._on_queue_changed()
                except Exception as e:
                    logger.warning(f"Error in queue change callback: {e}")

            logger.info(
                f"Processing request {request_id} "
                f"(queue={self.get_queue_depth()}, active={self.get_processing_count()})"
            )

            try:
                # Call the callback function to process request
                if self._callback is None:
                    raise RuntimeError("Callback not set, call start_worker() first")

                result = await self._callback(request)

                # Store successful result
                processing_time = asyncio.get_event_loop().time() - start_time
                self._results[request_id] = TranscriptionResponse(
                    request_id=request_id,
                    result=result,
                    error=None,
                    processing_time=processing_time,
                )

                logger.info(f"Request {request_id} completed in {processing_time:.2f}s")

            except Exception as e:
                # Store error result
                processing_time = asyncio.get_event_loop().time() - start_time
                error_msg = str(e)
                self._results[request_id] = TranscriptionResponse(
                    request_id=request_id,
                    result=None,
                    error=error_msg,
                    processing_time=processing_time,
                )

                logger.error(
                    f"Request {request_id} failed after {processing_time:.2f}s: {error_msg}",
                    exc_info=True,
                )

            finally:
                self._processing.remove(request_id)
                # Remove from processing_requests list
                if request in self._processing_requests:
                    self._processing_requests.remove(request)
                self._total_pending -= 1  # Decrement counter when request completes
                self._queue.task_done()

    def get_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dictionary with queue metrics
        """
        return {
            "queue_depth": self.get_queue_depth(),
            "processing_count": self.get_processing_count(),
            "max_queue_size": self._max_queue_size,
            "max_concurrent": self._max_concurrent,
            "results_cached": len(self._results),
        }

    def set_on_queue_changed(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Set callback to be called when queue changes.

        Args:
            callback: Async function to call when queue position changes
        """
        self._on_queue_changed = callback

    def get_pending_requests(self) -> list[TranscriptionRequest]:
        """Get list of pending requests in queue order.

        Returns:
            List of TranscriptionRequest objects in queue order
        """
        return self._pending_requests.copy()

    def get_estimated_wait_time_by_id(self, request_id: str, rtf: float) -> tuple[float, float]:
        """Calculate estimated wait time and processing time for a request.

        Args:
            request_id: Request ID to calculate time for
            rtf: Real-time factor for processing time estimation

        Returns:
            Tuple of (wait_time_seconds, processing_time_seconds)
        """
        # Find request index in pending list
        request_index = -1
        current_request = None
        for i, req in enumerate(self._pending_requests):
            if req.id == request_id:
                request_index = i
                current_request = req
                break

        if request_index < 0 or current_request is None:
            return (0.0, 0.0)

        # Calculate total duration of items currently being processed
        # (these need to finish before queue items can start)
        processing_duration = sum(r.duration_seconds for r in self._processing_requests)

        # Get requests ahead of this one in the pending queue
        items_ahead = self._pending_requests[:request_index]

        # Calculate total duration of items ahead in pending queue
        pending_duration_ahead = sum(r.duration_seconds for r in items_ahead)

        # Total duration = processing + pending ahead
        total_duration_ahead = processing_duration + pending_duration_ahead

        # Wait time = total processing time of items ahead / concurrent workers
        wait_time = (total_duration_ahead * rtf) / self._max_concurrent

        # Processing time of current request
        processing_time = current_request.duration_seconds * rtf

        return (wait_time, processing_time)

    def get_queue_position_by_id(self, request_id: str) -> int:
        """Get current queue position for a request.

        Args:
            request_id: Request ID to find

        Returns:
            Position in queue (1-based), or 0 if not found
        """
        for i, req in enumerate(self._pending_requests):
            if req.id == request_id:
                return i + 1
        return 0
