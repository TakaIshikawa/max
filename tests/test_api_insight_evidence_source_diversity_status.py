from __future__ import annotations

import json

from max.api import insight_evidence_source_diversity_status_to_json


def test_insight_evidence_source_diversity_status_handles_nested_and_flat_evidence() -> None:
    report = json.loads(
        insight_evidence_source_diversity_status_to_json(
            {
                "minimum_sources": 2,
                "max_dominant_share": 0.6,
                "insights": [{"insight_id": "nested", "evidence": [{"source": "a"}, {"source": "a"}, {"source": "b"}]}],
                "evidence": [{"insight_id": "flat", "source": "x"}, {"insight_id": "flat", "source": "x"}],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["summary"]["status"] == "warning"
    assert report["summary"]["insight_count"] == 2
    assert report["summary"]["under_diversified_count"] == 1
    assert report["summary"]["concentrated_count"] == 2
    assert report["insights"][0]["risk_reasons"]
    assert report["insights"][0]["source_counts"]
    assert report["status"] == "warning"
