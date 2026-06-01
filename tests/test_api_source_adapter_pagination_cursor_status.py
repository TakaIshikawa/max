from __future__ import annotations

import json

from max.api import source_adapter_pagination_cursor_status_to_json


def test_pagination_cursor_flattens_and_classifies() -> None:
    parsed = json.loads(source_adapter_pagination_cursor_status_to_json({"adapters": [
        {"adapter": "rss", "sources": [{"source": "ok", "lag_seconds": 10}, {"source": "dup", "duplicate_page_count": 3}]},
        {"adapter": "api", "sources": [{"source": "reset", "reset_required": True}, {"source": "stale", "lag_seconds": 5000, "stale_after_seconds": 1000}]},
    ]}))
    assert parsed["schema_version"] == "max.api.source_adapter_pagination_cursor_status.v1"
    assert parsed["summary"]["status"] == "critical"
    assert [row["source"] for row in parsed["affected_adapters"][:2]] == ["reset", "dup"]
    assert any(row["status"] == "healthy" for row in parsed["cursor_summaries"])
