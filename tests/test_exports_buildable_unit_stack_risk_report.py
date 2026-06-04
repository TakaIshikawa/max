from __future__ import annotations

from max.exports.buildable_unit_stack_risk_report import generate_buildable_unit_stack_risk_report


def test_accepts_stack_dependency_runtime_and_deployment_fields() -> None:
    report = generate_buildable_unit_stack_risk_report([{"unit_id": "u1", "stack": {"runtime": "python3.12", "dependencies": ["fastapi"], "deployment_target": "ecs"}}])
    assert report["rows"][0]["unit_id"] == "u1"
    assert report["rows"][0]["risk"] == "low"


def test_rows_include_required_risk_fields() -> None:
    report = generate_buildable_unit_stack_risk_report([{"id": "u1", "runtime": "python2", "dependencies": [{"status": "unknown"}]}])
    row = report["rows"][0]
    assert row["unsupported_runtime"] is True
    assert row["unknown_dependency_count"] == 1
    assert row["missing_deployment_target"] is True
    assert row["risk"] == "high"


def test_unknown_or_absent_stack_data_does_not_crash() -> None:
    report = generate_buildable_unit_stack_risk_report([{"unit_id": "u1"}])
    assert report["rows"][0]["unknown_dependency_count"] == 0
    assert report["rows"][0]["missing_deployment_target"] is True
    assert report["rows"][0]["risk"] == "medium"
