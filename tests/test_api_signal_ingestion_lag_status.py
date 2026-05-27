from __future__ import annotations

import json

from max.api.signal_ingestion_lag_status import signal_ingestion_lag_status_to_json


def test_signal_ingestion_lag_status_flags_stale_and_missing_rows() -> None:
    report = json.loads(
        signal_ingestion_lag_status_to_json(
            {
                "sources": [
                    {"source": "fresh", "newest_signal_at": "2026-05-27T00:00:00Z", "fetched_at": "2026-05-27T00:05:00Z", "lag_minutes": 5, "stale_threshold_minutes": 30, "signal_count": 4},
                    {"source": "stale", "newest_signal_at": "2026-05-27T00:00:00Z", "fetched_at": "2026-05-27T02:00:00Z", "lag_minutes": 120, "stale_threshold_minutes": 60, "signal_count": 3},
                    {"source": "missing", "lag_minutes": 0, "stale_threshold_minutes": 60, "signal_count": 0},
                ]
            }
        )
    )

    assert [row["source"] for row in report["rows"]] == ["missing", "stale", "fresh"]
    assert [row["status"] for row in report["rows"]] == ["missing", "stale", "fresh"]
    assert report["summary"]["total_sources"] == 3
    assert report["summary"]["stale_sources"] == 1
    assert report["summary"]["max_lag_minutes"] == 120.0
    json.dumps(report)
