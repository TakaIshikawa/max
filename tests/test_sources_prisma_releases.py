from __future__ import annotations

import pytest

from max.sources.prisma_releases import PrismaReleasesAdapter, parse_prisma_releases


def test_prisma_releases_emit_one_signal_per_entry() -> None:
    signals = parse_prisma_releases([{"version": "5.12.0", "title": "Prisma 5.12.0", "url": "https://github.com/prisma/prisma/releases/5.12.0", "published_at": "2026-05-01T00:00:00Z"}])
    assert len(signals) == 1
    assert signals[0].source_adapter == "prisma_releases"
    assert signals[0].metadata["version"] == "5.12.0"


def test_prisma_releases_capture_channel_and_package_metadata() -> None:
    signal = parse_prisma_releases([{"title": "Prisma 6.0.0 preview", "url": "https://prisma.io/release", "channel": "preview", "affected_package": "client"}])[0]
    assert signal.metadata["channel"] == "preview"
    assert signal.metadata["affected_package"] == "client"


def test_prisma_releases_limit_and_stable_ids() -> None:
    payload = [{"version": "5.1.0", "title": "Prisma 5.1.0", "url": "https://prisma.io/5.1.0"}, {"version": "5.2.0", "title": "Prisma 5.2.0", "url": "https://prisma.io/5.2.0"}]
    assert parse_prisma_releases(payload)[0].id == parse_prisma_releases(payload)[0].id


@pytest.mark.asyncio
async def test_prisma_releases_adapter_truncates_limit() -> None:
    signals = await PrismaReleasesAdapter(config={"entries": [{"title": "A", "url": "https://p/a"}, {"title": "B", "url": "https://p/b"}]}).fetch(limit=1)
    assert len(signals) == 1
