from __future__ import annotations

import json

from max.api.signal_annotation_status import (
    KIND,
    SCHEMA_VERSION,
    signal_annotation_status_to_json,
)


def test_signal_annotation_status_to_json_summarizes_and_sorts_sources() -> None:
    payload = {
        "schema_version": "max.signal_annotation_status.v1",
        "kind": "max.signal_annotation_status",
        "sources": [
            {"source": "rss", "total": 10, "annotated": 8, "problem": 3, "solution": 2, "market": 3, "unclassified": 2},
            {"source": "github", "total": 6, "annotated": 3, "problem": 1, "solution": 1, "market": 1, "unclassified": 3},
            {"source": "zendesk", "total": 4, "annotated": 1, "problem": 1, "solution": 0, "market": 0, "unclassified": 3},
        ],
    }

    output = signal_annotation_status_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {
        "annotated_signals": 12,
        "annotation_completion_percentage": 60.0,
        "source_count": 3,
        "total_signals": 20,
        "unclassified_signals": 8,
    }
    assert [row["source"] for row in parsed["sources"]] == ["github", "zendesk", "rss"]
    assert parsed["sources"][0]["annotation_completion_percentage"] == 50.0
    assert output == signal_annotation_status_to_json(payload)


def test_signal_annotation_status_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(signal_annotation_status_to_json({"source_annotations": [{}]}))

    assert parsed["sources"][0] == {
        "annotated_count": 0,
        "annotation_completion_percentage": 0.0,
        "market_count": 0,
        "metadata": {},
        "problem_count": 0,
        "solution_count": 0,
        "source": "source-1",
        "total_count": 0,
        "unclassified_count": 0,
    }
