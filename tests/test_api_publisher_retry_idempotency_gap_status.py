from __future__ import annotations

import json

from max.api.publisher_retry_idempotency_gap_status import publisher_retry_idempotency_gap_status_to_json


def test_publisher_retry_idempotency_gap_status_ratio_precedence_and_sort() -> None:
    parsed = json.loads(
        publisher_retry_idempotency_gap_status_to_json(
            {
                "destinations": [
                    {"destination": "ok", "retry_count": 1, "idempotency_key_count": 10, "missing_key_count": 0},
                    {"destination": "warn", "retry_count": 4, "idempotency_key_count": 9, "missing_key_count": 1},
                    {"destination": "dup-low-rate", "retry_count": 1, "idempotency_key_count": 100, "missing_key_count": 1, "duplicate_publication_count": 1},
                    {},
                ]
            },
            warning_missing_key_rate=0.05,
            retry_warning_count=3,
        )
    )

    assert [row["destination"] for row in parsed["destinations"]] == ["dup-low-rate", "warn", "destination-4", "ok"]
    assert parsed["destinations"][0]["status"] == "critical"
    assert parsed["destinations"][1]["missing_key_rate"] == 0.1
    assert parsed["summary"]["destinations_with_duplicates"] == 1
    assert parsed["summary"]["total_missing_key_count"] == 2
