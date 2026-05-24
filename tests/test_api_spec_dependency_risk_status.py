from __future__ import annotations

import json

from max.api.spec_dependency_risk_status import spec_dependency_risk_status_to_json


def test_spec_dependency_risk_status_derives_required_and_optional_states() -> None:
    parsed = json.loads(
        spec_dependency_risk_status_to_json(
            {
                "dependencies": [
                    {"spec_id": "s1", "dependency": "db", "owner": "data", "health": "healthy"},
                    {"spec_id": "s1", "dependency": "api", "owner": "platform", "health": "warning"},
                    {"spec_id": "s2", "dependency": "queue", "owner": "platform", "blockers": ["missing topic"]},
                    {"spec_id": "s3", "dependency": "docs", "required": "false", "health": "blocked"},
                ]
            }
        )
    )

    assert [row["dependency"] for row in parsed["dependencies"]] == ["queue", "api", "db", "docs"]
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["summary"]["optional_count"] == 1
    assert parsed["blocked_dependencies"][0]["blockers"] == ["missing topic"]
    assert parsed["owner_totals"][1]["owner"] == "platform"
    assert parsed["owner_totals"][1]["blocked_count"] == 1


def test_spec_dependency_risk_status_aliases_and_metadata() -> None:
    parsed = json.loads(spec_dependency_risk_status_to_json({"spec_dependencies": [{"spec": "s", "name": "dep", "health": "unhealthy"}]}, as_of="now"))

    assert parsed["dependencies"][0]["status"] == "blocked"
    assert parsed["spec_totals"][0]["spec_id"] == "s"
    assert parsed["metadata"]["as_of"] == "now"
