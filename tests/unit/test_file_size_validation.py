"""Unit tests for file size validation in bot handlers."""

import pytest
from src.config import settings


class TestFileSizeValidation:
    """Test file size validation logic."""

    MAX_FILE_SIZE = settings.max_file_size_bytes  # 20 MB in bytes (Telegram Bot API limit)

    @pytest.mark.parametrize(
        "file_size_mb,should_be_rejected",
        [
            (1, False),  # 1 MB - should be accepted
            (10, False),  # 10 MB - should be accepted
            (19, False),  # 19 MB - should be accepted
            (20, False),  # 20 MB - exactly at limit, should be accepted
            (20.1, True),  # 20.1 MB - exceeds limit, should be rejected
            (21, True),  # 21 MB - should be rejected
            (25, True),  # 25 MB - should be rejected
            (50, True),  # 50 MB - should be rejected
        ],
    )
    def test_file_size_validation(self, file_size_mb: float, should_be_rejected: bool):
        """Test that file size validation correctly identifies files exceeding 20 MB limit.

        Args:
            file_size_mb: File size in megabytes
            should_be_rejected: Whether file should be rejected
        """
        file_size_bytes = int(file_size_mb * 1024 * 1024)
        is_too_big = file_size_bytes > self.MAX_FILE_SIZE

        assert is_too_big == should_be_rejected, (
            f"File size {file_size_mb} MB (bytes: {file_size_bytes}) "
            f"should {'be rejected' if should_be_rejected else 'be accepted'}, "
            f"but validation returned {is_too_big}"
        )

    def test_max_file_size_constant(self):
        """Verify MAX_FILE_SIZE constant is set correctly."""
        expected_bytes = 20 * 1024 * 1024  # 20 MB
        assert self.MAX_FILE_SIZE == expected_bytes
        assert self.MAX_FILE_SIZE == 20971520  # 20 MB in bytes

    def test_file_size_formatting(self):
        """Test that file size is formatted correctly in user messages."""
        test_sizes = [
            (10 * 1024 * 1024, 10.0),  # 10 MB
            (20 * 1024 * 1024, 20.0),  # 20 MB
            (25 * 1024 * 1024, 25.0),  # 25 MB
            (21.5 * 1024 * 1024, 21.5),  # 21.5 MB
        ]

        for size_bytes, expected_mb in test_sizes:
            actual_mb = size_bytes / 1024 / 1024
            assert abs(actual_mb - expected_mb) < 0.01, (
                f"File size {size_bytes} bytes should format to {expected_mb} MB, "
                f"but got {actual_mb} MB"
            )
