from __future__ import annotations

import json

from max.api.source_fetch_starvation_status import source_fetch_starvation_status_to_json


def test_source_fetch_starvation_status_computes_gap_summary_and_sorting() -> None:
    report = json.loads(source_fetch_starvation_status_to_json({"sources": [{"source": "rss", "allocated_fetches": 9, "completed_fetches": 2, "skipped_fetches": 1, "target_min_fetches": 7}, {"source": "api", "allocated_fetches": "4", "completed_fetches": 4, "skipped_fetches": 0, "target_min_fetches": 4}, {"source": "db", "allocated_fetches": -2, "completed_fetches": "bad", "skipped_fetches": 1, "target_min_fetches": 3}]}))

    assert [row["source"] for row in report["rows"]] == ["rss", "db", "api"]
    assert [row["starvation_gap"] for row in report["rows"]] == [4, 2, 0]
    assert report["summary"]["total_allocated"] == 13
    assert report["summary"]["total_completed"] == 6
    assert report["summary"]["total_skipped"] == 2
    assert report["summary"]["starved_count"] == 2
