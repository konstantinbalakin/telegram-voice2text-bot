"""Tests for QueueManager."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.queue_manager import QueueManager, TranscriptionRequest, TranscriptionResponse
from src.transcription.models import TranscriptionContext


def _make_request(
    request_id: str = "req-1",
    user_id: int = 100,
    duration_seconds: int = 30,
) -> TranscriptionRequest:
    """Create a TranscriptionRequest with mocked Telegram objects."""
    return TranscriptionRequest(
        id=request_id,
        user_id=user_id,
        file_path=Path("/tmp/test.ogg"),
        duration_seconds=duration_seconds,
        context=TranscriptionContext(user_id=user_id, duration_seconds=duration_seconds),
        status_message=MagicMock(),
        user_message=MagicMock(),
        usage_id=1,
    )


class TestQueueManagerInit:
    """Tests for QueueManager initialization."""

    def test_init_defaults(self):
        qm = QueueManager()
        assert qm._max_queue_size == 50
        assert qm._max_concurrent == 1
        assert qm._worker_task is None
        assert qm._callback is None

    def test_init_custom_params(self):
        qm = QueueManager(max_queue_size=10, max_concurrent=3)
        assert qm._max_queue_size == 10
        assert qm._max_concurrent == 3


class TestEnqueue:
    """Tests for enqueue operations."""

    async def test_enqueue_returns_position_1(self):
        qm = QueueManager(max_queue_size=5)
        req = _make_request()
        position = await qm.enqueue(req)
        assert position == 1

    async def test_multiple_enqueue_incrementing_positions(self):
        qm = QueueManager(max_queue_size=5)
        positions = []
        for i in range(3):
            req = _make_request(request_id=f"req-{i}", user_id=100 + i)
            pos = await qm.enqueue(req)
            positions.append(pos)
        assert positions == [1, 2, 3]

    async def test_queue_full_blocks(self):
        """asyncio.Queue.put() blocks when full; verify enqueue doesn't complete immediately."""
        qm = QueueManager(max_queue_size=2)
        await qm.enqueue(_make_request(request_id="r1"))
        await qm.enqueue(_make_request(request_id="r2"))
        # Third enqueue should block (put() waits for space), so it times out
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                qm.enqueue(_make_request(request_id="r3")),
                timeout=0.1,
            )

    async def test_queue_depth_does_not_exceed_max(self):
        qm = QueueManager(max_queue_size=1)
        await qm.enqueue(_make_request(request_id="r1"))
        assert qm.get_queue_depth() == 1
        # Queue is full, verify depth stays at max
        assert qm._max_queue_size == 1


class TestQueueDepth:
    """Tests for get_queue_depth."""

    async def test_get_queue_depth_empty(self):
        qm = QueueManager()
        assert qm.get_queue_depth() == 0

    async def test_get_queue_depth_after_enqueue(self):
        qm = QueueManager(max_queue_size=5)
        await qm.enqueue(_make_request(request_id="r1"))
        await qm.enqueue(_make_request(request_id="r2"))
        assert qm.get_queue_depth() == 2


class TestWorkerLifecycle:
    """Tests for start_worker / stop_worker."""

    async def test_start_worker(self):
        qm = QueueManager()
        callback = AsyncMock()
        await qm.start_worker(callback)
        try:
            assert qm._worker_task is not None
            assert qm._callback is callback
        finally:
            await qm.stop_worker()

    async def test_stop_worker(self):
        qm = QueueManager()
        callback = AsyncMock()
        await qm.start_worker(callback)
        await qm.stop_worker()
        assert qm._worker_task is None

    async def test_start_worker_twice_is_noop(self):
        qm = QueueManager()
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        await qm.start_worker(callback1)
        try:
            original_task = qm._worker_task
            await qm.start_worker(callback2)
            # Should not replace the worker
            assert qm._worker_task is original_task
            assert qm._callback is callback1
        finally:
            await qm.stop_worker()

    async def test_stop_worker_when_not_started(self):
        qm = QueueManager()
        # Should not raise
        await qm.stop_worker()
        assert qm._worker_task is None


class TestRequestProcessing:
    """Tests for request processing via the worker."""

    async def test_processing_invokes_callback(self):
        qm = QueueManager(max_queue_size=5)
        mock_result = MagicMock()
        callback = AsyncMock(return_value=mock_result)

        await qm.start_worker(callback)
        try:
            req = _make_request(request_id="proc-1")
            await qm.enqueue(req)

            # Wait for processing to complete
            response = await asyncio.wait_for(
                qm.wait_for_result("proc-1", timeout=5.0, poll_interval=0.05),
                timeout=5.0,
            )

            callback.assert_called_once_with(req)
            assert response.request_id == "proc-1"
            assert response.result is mock_result
            assert response.error is None
        finally:
            await qm.stop_worker()

    async def test_get_result_after_processing(self):
        qm = QueueManager(max_queue_size=5)
        mock_result = MagicMock()
        callback = AsyncMock(return_value=mock_result)

        await qm.start_worker(callback)
        try:
            req = _make_request(request_id="res-1")
            await qm.enqueue(req)

            # Wait for processing
            await asyncio.wait_for(
                qm.wait_for_result("res-1", timeout=5.0, poll_interval=0.05),
                timeout=5.0,
            )
        finally:
            await qm.stop_worker()

        # After wait_for_result pops, get_result returns None
        assert qm.get_result("res-1") is None

    async def test_callback_error_stores_error_result(self):
        qm = QueueManager(max_queue_size=5)
        callback = AsyncMock(side_effect=RuntimeError("transcription failed"))

        await qm.start_worker(callback)
        try:
            req = _make_request(request_id="err-1")
            await qm.enqueue(req)

            response = await asyncio.wait_for(
                qm.wait_for_result("err-1", timeout=5.0, poll_interval=0.05),
                timeout=5.0,
            )

            assert response.request_id == "err-1"
            assert response.result is None
            assert response.error == "transcription failed"
        finally:
            await qm.stop_worker()


class TestGetStats:
    """Tests for get_stats."""

    def test_get_stats_initial(self):
        qm = QueueManager(max_queue_size=20, max_concurrent=2)
        stats = qm.get_stats()
        assert stats["queue_depth"] == 0
        assert stats["processing_count"] == 0
        assert stats["max_queue_size"] == 20
        assert stats["max_concurrent"] == 2
        assert stats["results_cached"] == 0
        assert stats["results_pending"] == 0

    async def test_get_stats_after_enqueue(self):
        qm = QueueManager(max_queue_size=10)
        await qm.enqueue(_make_request(request_id="s1"))
        await qm.enqueue(_make_request(request_id="s2"))
        stats = qm.get_stats()
        assert stats["queue_depth"] == 2


class TestQueuePositionById:
    """Tests for get_queue_position_by_id."""

    async def test_position_found(self):
        qm = QueueManager(max_queue_size=10)
        await qm.enqueue(_make_request(request_id="a"))
        await qm.enqueue(_make_request(request_id="b"))
        await qm.enqueue(_make_request(request_id="c"))

        assert qm.get_queue_position_by_id("a") == 1
        assert qm.get_queue_position_by_id("b") == 2
        assert qm.get_queue_position_by_id("c") == 3

    async def test_position_not_found(self):
        qm = QueueManager(max_queue_size=10)
        assert qm.get_queue_position_by_id("nonexistent") == 0


class TestEstimatedWaitTime:
    """Tests for get_estimated_wait_time_by_id."""

    async def test_wait_time_not_found(self):
        qm = QueueManager(max_queue_size=10)
        wait_time, proc_time = qm.get_estimated_wait_time_by_id("missing", rtf=0.5)
        assert wait_time == 0.0
        assert proc_time == 0.0

    async def test_wait_time_first_in_queue(self):
        qm = QueueManager(max_queue_size=10, max_concurrent=1)
        req = _make_request(request_id="first", duration_seconds=60)
        await qm.enqueue(req)

        wait_time, proc_time = qm.get_estimated_wait_time_by_id("first", rtf=0.5)
        # No items ahead, so wait_time = 0
        assert wait_time == 0.0
        # Processing time = 60 * 0.5 = 30.0
        assert proc_time == 30.0

    async def test_wait_time_second_in_queue(self):
        qm = QueueManager(max_queue_size=10, max_concurrent=1)
        await qm.enqueue(_make_request(request_id="first", duration_seconds=60))
        await qm.enqueue(_make_request(request_id="second", duration_seconds=30))

        wait_time, proc_time = qm.get_estimated_wait_time_by_id("second", rtf=0.5)
        # Wait = 60 * 0.5 / 1 = 30.0 (first item ahead)
        assert wait_time == 30.0
        # Processing = 30 * 0.5 = 15.0
        assert proc_time == 15.0


class TestProcessingCount:
    """Tests for get_processing_count."""

    def test_processing_count_initial(self):
        qm = QueueManager()
        assert qm.get_processing_count() == 0

    async def test_processing_count_during_processing(self):
        qm = QueueManager(max_queue_size=5)
        processing_started = asyncio.Event()
        processing_proceed = asyncio.Event()

        async def slow_callback(request: TranscriptionRequest) -> MagicMock:
            processing_started.set()
            await processing_proceed.wait()
            return MagicMock()

        await qm.start_worker(slow_callback)
        try:
            req = _make_request(request_id="slow-1")
            await qm.enqueue(req)

            # Wait for processing to start
            await asyncio.wait_for(processing_started.wait(), timeout=2.0)
            assert qm.get_processing_count() == 1

            # Let processing finish
            processing_proceed.set()
            await asyncio.wait_for(
                qm.wait_for_result("slow-1", timeout=5.0, poll_interval=0.05),
                timeout=5.0,
            )
            assert qm.get_processing_count() == 0
        finally:
            await qm.stop_worker()


class TestScheduleCleanup:
    """Tests for _schedule_cleanup (P3 feature)."""

    async def test_cleanup_removes_result_after_delay(self):
        qm = QueueManager()
        qm._results["test-id"] = TranscriptionResponse(
            request_id="test-id", result=None, error=None
        )
        assert "test-id" in qm._results

        # Run cleanup with very short delay
        await qm._schedule_cleanup("test-id", delay=0.01)
        assert "test-id" not in qm._results

    async def test_cleanup_noop_for_missing_id(self):
        qm = QueueManager()
        # Should not raise
        await qm._schedule_cleanup("nonexistent", delay=0.01)

    async def test_cleanup_scheduled_after_processing(self):
        qm = QueueManager(max_queue_size=5)
        mock_result = MagicMock()
        callback = AsyncMock(return_value=mock_result)

        await qm.start_worker(callback)
        try:
            req = _make_request(request_id="cleanup-1")
            await qm.enqueue(req)

            response = await asyncio.wait_for(
                qm.wait_for_result("cleanup-1", timeout=5.0, poll_interval=0.05),
                timeout=5.0,
            )
            assert response is not None
            # wait_for_result pops the result, so it's already gone
            assert qm.get_result("cleanup-1") is None
        finally:
            await qm.stop_worker()
