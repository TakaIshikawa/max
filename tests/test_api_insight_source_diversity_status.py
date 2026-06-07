from __future__ import annotations

import json

from max.api import insight_source_diversity_status_to_json


def test_insight_source_diversity_status_reports_critical_low_diversity() -> None:
    data = json.loads(insight_source_diversity_status_to_json({"min_distinct_sources": 2, "critical_low_diversity_count": 2, "insights": [{"insight_id": "i-1", "sources": ["github"]}, {"insight_id": "i-2", "distinct_source_count": 1}, {"insight_id": "i-3", "sources": ["github", "reddit"]}]}))

    assert data["status"] == "critical"
    assert data["min_distinct_sources"] == 2
    assert data["insight_count"] == 3
    assert data["low_diversity_count"] == 2
    assert data["worst_insight_id"] == "i-1"


def test_insight_source_diversity_status_supports_warning_and_ok() -> None:
    warning = json.loads(insight_source_diversity_status_to_json({"warning_low_diversity_count": 1, "critical_low_diversity_count": 3, "rows": [{"id": "i-1", "sources": ["github"]}]}))
    ok = json.loads(insight_source_diversity_status_to_json({"items": [{"id": "i-2", "sources": ["github", "reddit"]}]}))

    assert warning["status"] == "warning"
    assert ok["status"] == "ok"
    assert ok["worst_insight_id"] is None
