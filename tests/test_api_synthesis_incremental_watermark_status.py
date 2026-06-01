from __future__ import annotations

import json

from max.api import synthesis_incremental_watermark_status_to_json


def test_synthesis_incremental_watermark_status_calculates_lag_and_blockers() -> None:
    report = json.loads(synthesis_incremental_watermark_status_to_json({"as_of": "2026-06-01T12:00:00Z", "max_lag_hours": 4, "sources": [{"source": "ok", "watermark_at": "2026-06-01T10:00:00Z", "latest_signal_at": "2026-06-01T11:00:00Z", "updated_at": "2026-06-01T11:00:00Z"}, {"source": "lag", "watermark_at": "2026-06-01T00:00:00Z", "latest_signal_at": "2026-06-01T11:00:00Z", "updated_at": "2026-06-01T11:00:00Z"}, {"source": "missing"}]}))
    assert report["overall_status"] == "critical"
    assert report["max_lag_hours"] == 11.0
    assert report["missing_watermark_count"] == 1
    assert [row["source"] for row in report["blockers"]] == ["missing"]
