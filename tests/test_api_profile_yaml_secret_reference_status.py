from __future__ import annotations

import json

from max.api.profile_yaml_secret_reference_status import profile_yaml_secret_reference_status_to_json


def test_profile_yaml_secret_reference_status_normalizes_and_prioritizes() -> None:
    parsed = json.loads(
        profile_yaml_secret_reference_status_to_json(
            {
                "profiles": [
                    {"profile": "ok", "secret_references": ["b", "a"], "required_reference_count": 2},
                    {"profile": "warn", "secret_references": "db", "unresolved_references": ["db"], "required_reference_count": 1},
                    {"profile": "critical", "plaintext_secret_count": 1, "unresolved_references": ["also-warning"]},
                    {},
                ]
            }
        )
    )

    assert [row["profile"] for row in parsed["profiles"]] == ["critical", "warn", "ok", "profile-4"]
    assert parsed["profiles"][0]["status"] == "critical"
    assert parsed["profiles"][1]["secret_references"] == ["db"]
    assert parsed["summary"]["profiles_with_plaintext_secrets"] == 1
    assert parsed["summary"]["profiles_with_unresolved_references"] == 2
