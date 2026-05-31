from __future__ import annotations

import json

from max.api.insight_evidence_coverage_status import insight_evidence_coverage_status_to_json


def test_insight_evidence_coverage_status_summarizes_under_supported_insights() -> None:
    report = json.loads(
        insight_evidence_coverage_status_to_json(
            {
                "insights": [
                    {"insight_id": "good", "evidence_ids": ["e1", "e2"], "source_ids": ["github", "hn", "github"]},
                    {"insight_id": "thin", "evidence_ids": ["e1"], "source_ids": ["github"]},
                    {"insight_id": "broken", "evidence_count": 3, "source_ids": ["github", "hn"], "missing_evidence_chain": True},
                ]
            }
        )
    )

    assert [row["insight_id"] for row in report["rows"]] == ["broken", "thin", "good"]
    assert report["rows"][2]["source_count"] == 2
    assert report["summary"]["total_insights"] == 3
    assert report["summary"]["under_supported_count"] == 2
    assert report["summary"]["missing_evidence_count"] == 1
    assert report["summary"]["average_evidence_count"] == 2.0
