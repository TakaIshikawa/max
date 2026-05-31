from __future__ import annotations

import json

from max.api import source_sampling_bias_status_to_json


def test_source_sampling_bias_status_flags_share_delta_over_threshold() -> None:
    data = json.loads(source_sampling_bias_status_to_json({"bias_threshold": 0.1, "sources": [{"source": "docs", "sample_count": 80, "expected_share": 0.5}, {"source": "tickets", "sample_count": 20, "expected_share": 0.5}]}))

    assert data["summary"]["biased_source_count"] == 2
    assert data["rows"][0]["biased"] is True
    assert data["summary"]["status"] == "biased"


def test_source_sampling_bias_status_tolerates_missing_numeric_fields_and_sorts_stably() -> None:
    data = json.loads(source_sampling_bias_status_to_json({"items": [{"source": "b"}, {"source": "a", "profile": "p"}]}))

    assert [row["source"] for row in data["rows"]] == ["a", "b"]
    assert data["summary"]["source_count"] == 2
