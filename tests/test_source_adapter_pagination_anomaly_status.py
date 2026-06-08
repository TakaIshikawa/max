from __future__ import annotations

import json

from max.api.source_adapter_pagination_anomaly_status import source_adapter_pagination_anomaly_status_to_json


def test_source_adapter_pagination_anomaly_status_clean_runs() -> None:
    report = json.loads(source_adapter_pagination_anomaly_status_to_json({"runs": [{"adapter": "rss", "run_id": "1"}]}))

    assert report["runs"][0]["status"] == "healthy"


def test_source_adapter_pagination_anomaly_status_warning_and_critical() -> None:
    report = json.loads(source_adapter_pagination_anomaly_status_to_json({"runs": [{"adapter": "warn", "run_id": "2", "duplicate_page_count": 1}, {"adapter": "crit", "run_id": "1", "repeated_cursor_count": 3}]}))

    assert [row["status"] for row in report["runs"]] == ["critical", "warning"]
    assert report["summary"]["status"] == "critical"


def test_source_adapter_pagination_anomaly_status_deterministic_ordering() -> None:
    report = json.loads(source_adapter_pagination_anomaly_status_to_json({"runs": [{"adapter": "b", "run_id": "2", "skipped_page_count": 1}, {"adapter": "a", "run_id": "1", "skipped_page_count": 1}]}))

    assert [(row["adapter"], row["run_id"]) for row in report["runs"]] == [("a", "1"), ("b", "2")]
