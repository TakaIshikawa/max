from __future__ import annotations

import json

from max.api import evaluation_rubric_version_status_to_json


def test_evaluation_rubric_version_status_precedence_and_sorting() -> None:
    parsed = json.loads(
        evaluation_rubric_version_status_to_json(
            {
                "active_version": "v3",
                "profiles": [
                    {"profile": "current", "rubric_version": "v3"},
                    {"profile": "old", "rubric_version": "v2"},
                    {"profile": "mixed", "versions": ["v3", "v2"]},
                    {"profile": "missing"},
                ],
            }
        )
    )

    assert [row["status"] for row in parsed["profiles"]] == ["missing", "mixed", "outdated", "current"]
    assert parsed["affected_profiles"] == ["missing", "mixed", "old"]
    assert parsed["summary"]["missing_count"] == 1

