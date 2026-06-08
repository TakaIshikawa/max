from __future__ import annotations

import json

from max.api.synthesis_throughput_status import synthesis_throughput_status_to_json


def test_synthesis_throughput_status_normal_throughput() -> None:
    report = json.loads(synthesis_throughput_status_to_json({"windows": [{"profile": "core", "window": "1h", "signals_processed": 20, "insights_generated": 5, "window_hours": 1}]}))

    assert report["windows"][0]["throughput_per_hour"] == 20
    assert report["windows"][0]["status"] == "healthy"


def test_synthesis_throughput_status_stalled_and_backlog_pressure() -> None:
    report = json.loads(synthesis_throughput_status_to_json({"windows": [{"profile": "core", "window": "stalled", "signals_processed": 0, "window_hours": 1, "backlog_count": 1}, {"profile": "growth", "window": "backlog", "signals_processed": 20, "window_hours": 1, "backlog_count": 100}]}))

    assert [row["status"] for row in report["windows"]] == ["stalled", "degraded"]
    assert report["summary"]["status"] == "stalled"


def test_synthesis_throughput_status_empty_windows() -> None:
    report = json.loads(synthesis_throughput_status_to_json({"windows": []}))

    assert report["summary"]["status"] == "idle"
