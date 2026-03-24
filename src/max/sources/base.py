"""Base source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from max.types.signal import Signal


class SourceAdapter(ABC):
    """Common interface for all signal sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter identifier (e.g. 'hackernews', 'npm_registry')."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Signal source type category."""

    @abstractmethod
    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        """Fetch signals from the source. Returns normalized Signal objects."""
