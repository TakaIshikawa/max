from __future__ import annotations

import json

from max.api import source_ingestion_error_taxonomy_status_to_json


def test_source_ingestion_error_taxonomy_status_clean_input() -> None:
    parsed = json.loads(source_ingestion_error_taxonomy_status_to_json({"errors": []}))

    assert parsed["summary"]["status"] == "clean"
    assert parsed["adapter_totals"] == []


def test_source_ingestion_error_taxonomy_status_noisy_and_failing() -> None:
    parsed = json.loads(
        source_ingestion_error_taxonomy_status_to_json(
            {
                "errors": [
                    {"adapter": "a", "category": "timeout", "severity": "low", "retryable": True, "count": 3},
                    {"adapter": "b", "category": "auth", "severity": "high", "retryable": False, "count": 2},
                ]
            }
        )
    )

    assert parsed["summary"]["status"] == "failing"
    assert parsed["summary"]["retryable_count"] == 3
    assert parsed["adapter_totals"][0]["adapter"] == "b"

