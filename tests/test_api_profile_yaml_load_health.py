from __future__ import annotations

import json

from max.api.profile_yaml_load_health import profile_yaml_load_health_to_json


def test_profile_yaml_load_health_failed_profiles_are_unhealthy() -> None:
    parsed = json.loads(
        profile_yaml_load_health_to_json(
            {
                "profiles": [
                    {"id": "b", "path": "b.yml", "warnings": ["deprecated"], "source_count": 2},
                    {"id": "a", "path": "a.yml", "missing_sections": ["signals"], "source_count": 1},
                ]
            }
        )
    )

    assert parsed["summary"]["status"] == "unhealthy"
    assert [row["profile_id"] for row in parsed["profiles"]] == ["a", "b"]
    assert parsed["missing_required_sections"] == [{"profile_id": "a", "sections": ["signals"]}]


def test_profile_yaml_load_health_warnings_degrade_without_failures() -> None:
    parsed = json.loads(profile_yaml_load_health_to_json({"profiles": [{"id": "a", "warnings": ["slow include"]}]}))

    assert parsed["summary"]["status"] == "degraded"
    assert parsed["summary"]["warned_count"] == 1


def test_profile_yaml_load_health_duplicate_ids_are_deterministic() -> None:
    parsed = json.loads(profile_yaml_load_health_to_json({"results": [{"profile_id": "z", "path": "2.yml"}, {"profile_id": "z", "path": "1.yml"}]}))

    assert parsed["duplicate_profile_ids"] == [{"profile_id": "z", "count": 2, "paths": ["1.yml", "2.yml"]}]
    assert parsed["summary"]["status"] == "unhealthy"
