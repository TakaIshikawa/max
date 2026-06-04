from __future__ import annotations

import json

from max.api.insight_contradiction_resolution_status import insight_contradiction_resolution_status_to_json


def test_insight_contradiction_resolution_status_state_evidence_and_sorting() -> None:
    parsed = json.loads(
        insight_contradiction_resolution_status_to_json(
            {
                "items": [
                    {"contradiction_id": "resolved-old", "resolution_state": "Resolved", "age_hours": 999, "evidence_count": 0},
                    {"contradiction_id": "thin", "resolution_state": "open", "age_hours": 1, "evidence_count": 1},
                    {"contradiction_id": "old", "state": "investigating", "age_hours": 100, "conflicting_insight_ids": "i-1"},
                    {},
                ]
            },
            warning_age_hours=24,
            critical_age_hours=72,
            min_evidence_count=2,
        )
    )

    assert [row["contradiction_id"] for row in parsed["contradictions"]] == ["old", "thin", "contradiction-4", "resolved-old"]
    assert parsed["contradictions"][0]["status"] == "critical"
    assert parsed["contradictions"][0]["conflicting_insight_ids"] == ["i-1"]
    assert parsed["contradictions"][-1]["status"] == "ok"
    assert parsed["summary"]["open_contradiction_count"] == 3
