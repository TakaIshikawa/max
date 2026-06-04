from __future__ import annotations

import json

from max.api.profile_evidence_role_coverage_status import profile_evidence_role_coverage_status_to_json


def test_profile_evidence_role_coverage_status_normalizes_roles_and_deduplicates() -> None:
    report = json.loads(
        profile_evidence_role_coverage_status_to_json(
            [
                {"profile_id": "complete", "role": "Problem", "evidence_id": "e1"},
                {"profile_id": "complete", "role": "problem", "evidence_id": "e1"},
                {"profile_id": "complete", "role": "SOLUTION", "evidence_id": "e2"},
                {"profile_id": "complete", "role": "market_evidence", "evidence_id": "e3"},
                {"profile_id": "partial", "role": "problem", "evidence_id": "e4"},
            ]
        )
    )

    assert [row["profile_id"] for row in report["profiles"]] == ["partial", "complete"]
    assert report["profiles"][1]["role_counts"]["problem"] == 1
    assert report["profiles"][1]["coverage_ratio"] == 1.0

