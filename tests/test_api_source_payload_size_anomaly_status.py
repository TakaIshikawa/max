from __future__ import annotations

import json

from max.api.source_payload_size_anomaly_status import source_payload_size_anomaly_status_to_json


def test_source_payload_size_anomaly_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(source_payload_size_anomaly_status_to_json({"sources": {"rss": {"latest_payload_bytes": 120, "baseline_payload_bytes": 100}, "api": {"latest_payload_bytes": 300, "median_payload_bytes": 100}, "docs": {"latest_payload_bytes": 200, "baseline_payload_bytes": 100}}}, warning_ratio=1.5, critical_ratio=2.5))

    assert [row["source"] for row in report["source_rows"]] == ["api", "docs", "rss"]
    assert report["source_rows"][0]["size_ratio"] == 3.0
    assert report["source_rows"][0]["status"] == "critical"
    assert report["summary"]["anomalous_sources"] == 2


def test_source_payload_size_anomaly_status_handles_list_and_zero_baseline() -> None:
    report = json.loads(source_payload_size_anomaly_status_to_json({"sources": [{"source": "new", "latest_payload_bytes": 10, "baseline_payload_bytes": 0}, {"source": "empty", "latest_payload_bytes": 0, "baseline_payload_bytes": 0}]}))

    assert [row["source"] for row in report["source_rows"]] == ["new", "empty"]
    assert report["source_rows"][0]["size_ratio"] is None
    assert report["source_rows"][0]["status"] == "critical"
    assert report["source_rows"][1]["size_ratio"] == 1.0
    assert report["source_rows"][1]["status"] == "ok"
