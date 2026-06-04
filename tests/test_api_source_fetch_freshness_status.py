from __future__ import annotations

import json

from max.api.source_fetch_freshness_status import source_fetch_freshness_status_to_json


def test_source_fetch_freshness_status_empty_input_is_ok() -> None:
    report = json.loads(source_fetch_freshness_status_to_json([], now="2026-01-02T00:00:00Z"))

    assert report["status"] == "ok"
    assert report["summary"]["total_count"] == 0
    assert report["sources"] == []


def test_source_fetch_freshness_status_classifies_and_sorts_sources() -> None:
    report = json.loads(
        source_fetch_freshness_status_to_json(
            [
                {"source": "fresh", "seen_at": "2026-01-01T23:00:00Z"},
                {"source": "stale", "seen_at": "2025-12-30T00:00:00Z"},
                {"source": "stale", "seen_at": "bad"},
                {"source": "mixed", "seen_at": "2026-01-01T22:00:00Z"},
                {"source": "mixed", "seen_at": "2025-12-30T00:00:00Z"},
            ],
            now="2026-01-02T00:00:00Z",
        )
    )

    assert [row["source"] for row in report["sources"]] == ["stale", "mixed", "fresh"]
    assert report["sources"][0]["malformed_timestamp_count"] == 1
    assert report["sources"][0]["stale_ratio"] == 1.0
    assert report["sources"][-1]["status"] == "ok"

