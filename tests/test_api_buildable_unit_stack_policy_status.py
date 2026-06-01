from __future__ import annotations

import json

from max.api import buildable_unit_stack_policy_status_to_json


def test_buildable_unit_stack_policy_status_checks_allowed_and_blocked_case_insensitively() -> None:
    rendered = json.loads(buildable_unit_stack_policy_status_to_json({"allowed_stacks": ["Python"], "blocked_dependencies": ["Log4J"], "required_runtime": "3.12", "units": [{"unit": "bad", "stack": ["python", "Log4j"], "runtime": "3.11"}, {"unit": "ok", "stack": ["PYTHON"], "runtime": "3.12"}]}))

    assert rendered["schema_version"] == "max.api.buildable_unit_stack_policy_status.v1"
    assert rendered["kind"] == "max.api.buildable_unit_stack_policy_status"
    assert rendered["summary"]["unit_count"] == 2
    assert rendered["summary"]["violating_unit_count"] == 1
    assert rendered["summary"]["blocked_dependency_count"] == 1
    assert rendered["summary"]["status"] == "critical"
    assert rendered["violating_units"][0]["unit"] == "bad"
