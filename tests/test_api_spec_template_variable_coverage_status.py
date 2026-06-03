from __future__ import annotations

import json

from max.api import spec_template_variable_coverage_status_to_json


def test_spec_template_variable_coverage_status_normalizes_missing_variables() -> None:
    data = json.loads(spec_template_variable_coverage_status_to_json({"templates": [{"template": "a", "required_variable_count": 10, "populated_variable_count": 7, "missing_variables": "profile"}, {"template": "b", "required_variable_count": 10, "populated_variable_count": 9, "missing_variables": ["z", "a"]}, {"template": "c", "required_variable_count": 0, "populated_variable_count": 0}]}))
    assert data["summary"] == {"status": "critical", "template_count": 3, "incomplete_template_count": 2, "critical_count": 1, "warning_count": 1, "lowest_coverage_ratio": 0.7}
    assert [row["template"] for row in data["templates"]] == ["a", "b", "c"]
    assert data["templates"][0]["missing_variables"] == ["profile"]
    assert data["templates"][1]["missing_variables"] == ["a", "z"]
