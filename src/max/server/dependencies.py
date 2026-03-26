"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import Generator

from max.store.db import Store


def get_store() -> Generator[Store, None, None]:
    """Yield a WAL-mode Store per request, close on teardown."""
    store = Store(wal_mode=True)
    try:
        yield store
    finally:
        store.close()
