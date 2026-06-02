from __future__ import annotations

import pytest

from max.sources.openai_status_incidents import OpenAIStatusIncidentsAdapter
from max.sources.registry import get_adapter, reload_registry


@pytest.mark.asyncio
async def test_openai_status_incidents_preserve_active_and_resolved_metadata() -> None:
    signals = await OpenAIStatusIncidentsAdapter({"entries": [
        {"title": "API errors", "url": "https://status.example/incidents/1", "status": "Investigating", "components": ["API"], "started_at": "2026-05-01T00:00:00Z"},
        {"title": "ChatGPT latency", "url": "https://status.example/incidents/2", "status": "Resolved", "components": ["ChatGPT"], "started_at": "2026-05-02T00:00:00Z", "resolved_at": "2026-05-02T01:00:00Z"},
    ]}).fetch()

    assert [signal.source_adapter for signal in signals] == ["openai_status_incidents", "openai_status_incidents"]
    assert signals[0].metadata["status"] == "investigating"
    assert signals[0].metadata["components"] == ["API"]
    assert signals[1].metadata["status"] == "resolved"
    assert signals[1].metadata["resolved_at"] == "2026-05-02T01:00:00+00:00"


def test_openai_status_incidents_registry_instantiates_adapter() -> None:
    reload_registry()
    assert get_adapter("openai_status_incidents").name == "openai_status_incidents"
