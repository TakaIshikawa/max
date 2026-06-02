from __future__ import annotations

import json

from max.api import signal_freshness_by_source_status_to_json


def test_signal_freshness_handles_missing_and_disabled_sources() -> None:
    report = json.loads(signal_freshness_by_source_status_to_json({"as_of": "2026-06-01T12:00:00Z", "sources": [{"source": "fresh", "newest_signal_at": "2026-06-01T06:00:00Z", "freshness_sla_hours": 24, "signal_count": 5}, {"source": "missing", "freshness_sla_hours": 24, "signal_count": 0}, {"source": "disabled", "enabled": False, "signal_count": 0}]}))

    rows = {row["source"]: row for row in report["sources"]}
    assert rows["fresh"]["age_hours"] == 6.0
    assert rows["missing"]["status"] == "critical"
    assert rows["disabled"]["status"] == "disabled"
    assert report["summary"]["critical_count"] == 1
