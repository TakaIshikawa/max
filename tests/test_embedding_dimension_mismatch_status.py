from __future__ import annotations

import json

from max.api import embedding_dimension_mismatch_status_to_json as exported
from max.api.embedding_dimension_mismatch_status import embedding_dimension_mismatch_status_to_json


def test_embedding_dimension_mismatch_status_handles_empty_records() -> None:
    report = json.loads(embedding_dimension_mismatch_status_to_json([]))

    assert exported is embedding_dimension_mismatch_status_to_json
    assert report["summary"]["status"] == "compatible"
    assert report["indexes"] == []


def test_embedding_dimension_mismatch_status_groups_and_uses_expected_lookup() -> None:
    report = json.loads(
        embedding_dimension_mismatch_status_to_json(
            {
                "expected_dimensions": {"ideas": 1536},
                "records": [
                    {"index_name": "ideas", "provider": "openai", "record_id": "b", "actual_dimensions": 768},
                    {"index_name": "ideas", "provider": "openai", "record_id": "a", "actual_dimensions": 1536},
                ],
            }
        )
    )

    assert report["indexes"][0]["index_name"] == "ideas"
    assert report["indexes"][0]["mismatch_count"] == 1
    assert report["indexes"][0]["mismatch_rate"] == 50
    assert report["indexes"][0]["affected_record_ids"] == ["b"]
    assert report["indexes"][0]["status"] == "incompatible"


def test_embedding_dimension_mismatch_status_sorts_drifted_before_compatible() -> None:
    report = json.loads(embedding_dimension_mismatch_status_to_json([{"index": "ok", "provider": "p", "expected_dimensions": 3, "dimensions": 3}, {"index": "bad", "provider": "p", "expected_dimensions": 3, "dimensions": 2}]))

    assert [row["index_name"] for row in report["indexes"]] == ["bad", "ok"]
