from __future__ import annotations

import json

from max.api.source_adapter_backfill_completeness_status import source_adapter_backfill_completeness_status_to_json


def test_source_adapter_backfill_completeness_status_complete() -> None:
    report = json.loads(source_adapter_backfill_completeness_status_to_json({"adapters": [{"adapter": "rss", "requested_range": {"start": 0, "end": 10}, "fetched_intervals": [{"start": 0, "end": 10}]}]}))

    assert report["adapters"][0]["completeness_ratio"] == 1.0
    assert report["adapters"][0]["status"] == "complete"


def test_source_adapter_backfill_completeness_status_partial_gaps() -> None:
    report = json.loads(source_adapter_backfill_completeness_status_to_json({"adapters": [{"adapter": "api", "requested_range": {"start": 0, "end": 10}, "fetched_intervals": [{"start": 0, "end": 3}, {"start": 7, "end": 10}]}]}))

    assert report["adapters"][0]["missing_intervals"] == [{"start": 3, "end": 7}]
    assert report["adapters"][0]["completeness_ratio"] == 0.6


def test_source_adapter_backfill_completeness_status_no_fetched_intervals_and_sorting() -> None:
    report = json.loads(source_adapter_backfill_completeness_status_to_json({"adapters": [{"adapter": "z", "requested_range": {"start": 0, "end": 5}, "fetched_intervals": [{"start": 0, "end": 5}]}, {"adapter": "a", "requested_range": {"start": 0, "end": 5}, "fetched_intervals": []}]}))

    assert [row["adapter"] for row in report["adapters"]] == ["a", "z"]
    assert report["adapters"][0]["missing_intervals"] == [{"start": 0, "end": 5}]
