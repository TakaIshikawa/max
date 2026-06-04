from __future__ import annotations

import json

from max.api import source_adapter_error_taxonomy_status_to_json


def test_source_adapter_error_taxonomy_status_normalizes_categories_and_summary() -> None:
    report = json.loads(source_adapter_error_taxonomy_status_to_json({"adapters": [{"source": "slack", "adapter": "api", "error_counts": {"auth": 9, "parse": 1}, "last_error_at": "2026-01-01"}, {"source": "rss", "error_counts": {"weird": 2}}, {"source": "ok"}]}, total_error_threshold=10, dominant_share_threshold=0.8))

    assert [row["source"] for row in report["adapter_rows"]] == ["slack", "rss", "ok"]
    assert [row["status"] for row in report["adapter_rows"]] == ["critical", "warning", "ok"]
    assert report["adapter_rows"][1]["dominant_error_category"] == "unknown"
    assert report["summary"]["dominant_error_categories"]["unknown"] == 2
