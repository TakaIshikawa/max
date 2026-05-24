from __future__ import annotations

import json

from max.api.signal_ingestion_lag import (
    KIND,
    SCHEMA_VERSION,
    signal_ingestion_lag_to_json,
)


def test_signal_ingestion_lag_to_json_groups_lag_by_source() -> None:
    payload = {
        "schema_version": "max.signal_ingestion_lag.v1",
        "kind": "max.signal_ingestion_lag",
        "stale_threshold_seconds": 600,
        "signals": [
            {
                "id": "s2",
                "source": "rss",
                "observed_at": "2026-05-20T00:00:00Z",
                "fetched_at": "2026-05-20T00:05:00Z",
                "stored_at": "2026-05-20T00:10:00Z",
            },
            {
                "id": "s1",
                "source": "github",
                "observed_at": "2026-05-20T00:00:00Z",
                "fetched_at": "2026-05-20T00:01:00Z",
                "stored_at": "2026-05-20T00:02:00Z",
            },
        ],
    }

    output = signal_ingestion_lag_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["lag_by_source"] == [
        {
            "average_lag_seconds": 120.0,
            "incomplete_record_count": 0,
            "max_lag_seconds": 120,
            "record_count": 1,
            "source": "github",
            "stale": False,
        },
        {
            "average_lag_seconds": 600.0,
            "incomplete_record_count": 0,
            "max_lag_seconds": 600,
            "record_count": 1,
            "source": "rss",
            "stale": True,
        },
    ]
    assert parsed["summary"]["stale_source_count"] == 1
    assert output == signal_ingestion_lag_to_json(payload)


def test_signal_ingestion_lag_to_json_counts_missing_timestamps() -> None:
    parsed = json.loads(signal_ingestion_lag_to_json({"signal_timings": [{"source": "rss"}]}))

    assert parsed["signal_lag_records"][0]["signal_id"] == "signal-1"
    assert parsed["signal_lag_records"][0]["missing_timestamp_count"] == 3
    assert parsed["incomplete_records"][0]["source"] == "rss"
    assert parsed["lag_by_source"][0]["average_lag_seconds"] is None
