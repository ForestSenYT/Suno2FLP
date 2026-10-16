"""MCP boundary; available tools must be negotiated with the actual server."""

from typing import Protocol

from suno2flp.core.models import BackendCapabilities


class DAWController(Protocol):
    def connect(self) -> BackendCapabilities:
        """Perform a real handshake or raise IntegrationUnavailableError."""
        ...

    def capabilities(self) -> BackendCapabilities:
        """Return observed operations and evidence, not assumed MCP functionality."""
        ...

    def disconnect(self) -> None:
        """Release the connection without modifying the active project."""
        ...
