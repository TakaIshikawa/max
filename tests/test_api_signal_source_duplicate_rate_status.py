from __future__ import annotations

import json

from max.api import signal_source_duplicate_rate_status_to_json


def test_signal_source_duplicate_rate_status_reports_critical_worst_source() -> None:
    data = json.loads(signal_source_duplicate_rate_status_to_json({"warning_duplicate_rate": 0.1, "critical_duplicate_rate": 0.3, "sources": [{"source": "github", "signal_count": 10, "duplicate_count": 1}, {"source": "reddit", "duplicate_rate": 0.4}]}))

    assert data["status"] == "critical"
    assert data["threshold"] == 0.1
    assert data["worst_source"] == "reddit"
    assert data["duplicate_rate"] == 0.4
    assert data["source_count"] == 2


def test_signal_source_duplicate_rate_status_supports_warning_and_ok() -> None:
    warning = json.loads(signal_source_duplicate_rate_status_to_json({"warning_duplicate_rate": 0.1, "critical_duplicate_rate": 0.3, "rows": [{"source_id": "hn", "signal_count": 10, "duplicate_count": 2}]}))
    ok = json.loads(signal_source_duplicate_rate_status_to_json({}))

    assert warning["status"] == "warning"
    assert warning["duplicate_rate"] == 0.2
    assert ok["status"] == "ok"
    assert ok["source_count"] == 0
