from __future__ import annotations

import json

from max.exports import generate_domain_profile_constraint_violation_report
from max.exports.domain_profile_constraint_violation_report import render_domain_profile_constraint_violation_report_json, render_domain_profile_constraint_violation_report_markdown


def test_domain_profile_constraint_violation_identifies_constraints_and_severity() -> None:
    report = generate_domain_profile_constraint_violation_report([{"profile": "regulated", "item_id": "idea-1", "status": "published", "stacks": ["redis", "rails"], "user_segment": "smb", "regulated_data": True, "constraints": {"excluded_stacks": ["redis"], "required_user_segment": "enterprise", "allow_regulated_data": False}}])

    assert [row["violation_type"] for row in report["rows"]] == ["excluded_stack", "missing_required_segment", "regulated_data"]
    assert all(row["severity"] == "critical" for row in report["rows"])
    assert "regulated / idea-1" in render_domain_profile_constraint_violation_report_markdown(report)
    json.loads(render_domain_profile_constraint_violation_report_json(report))
