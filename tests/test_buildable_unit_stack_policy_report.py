from __future__ import annotations

from max.exports import generate_buildable_unit_stack_policy_report as exported
from max.exports.buildable_unit_stack_policy_report import generate_buildable_unit_stack_policy_report


def test_buildable_unit_stack_policy_report_counts_decisions_and_status() -> None:
    report = generate_buildable_unit_stack_policy_report(
        [
            {"profile": "b2b", "unit_id": "unit-a", "checks": [{"technology": "Django", "decision": "allowed"}, {"technology": "Redis", "decision": "discouraged"}]},
            {"profile": "b2b", "unit_id": "unit-b", "checks": [{"technology": "PHP", "decision": "disallowed", "policy": "legacy-runtime"}]},
        ]
    )

    assert exported is generate_buildable_unit_stack_policy_report
    assert report["rows"] == [
        {"profile": "b2b", "buildable_unit_id": "unit-a", "technologies": ["Django", "Redis"], "allowed_count": 1, "discouraged_count": 1, "disallowed_count": 0, "violated_policies": [], "status": "warning"},
        {"profile": "b2b", "buildable_unit_id": "unit-b", "technologies": ["PHP"], "allowed_count": 0, "discouraged_count": 0, "disallowed_count": 1, "violated_policies": ["legacy-runtime"], "status": "violation"},
    ]


def test_buildable_unit_stack_policy_report_empty_input() -> None:
    assert generate_buildable_unit_stack_policy_report([])["summary"]["row_count"] == 0
