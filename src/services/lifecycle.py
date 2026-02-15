"""Unified lifecycle protocol for async services."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AsyncService(Protocol):
    """Protocol for services with async lifecycle management."""

    async def initialize(self) -> None:
        """Initialize the service (load resources, connect)."""
        ...

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup resources."""
        ...

    def is_initialized(self) -> bool:
        """Check if the service is initialized and ready."""
        ...
