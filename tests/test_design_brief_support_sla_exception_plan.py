from __future__ import annotations

import json

from max.analysis.design_brief_support_sla_exception_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_support_sla_exception_plan,
)


def test_support_sla_exception_plan_normalizes_complete_input() -> None:
    plan = generate_design_brief_support_sla_exception_plan(
        {
            "metadata": {
                "support_sla_exception_plan": {
                    "exceptions": [{"name": "weekend pause"}, {"name": "priority downgrade"}],
                    "affected_segments": [{"name": "beta customers"}],
                    "coverage_rules": [{"name": "pager coverage", "owner": "Support"}],
                    "escalation_owners": [{"name": "Support manager"}],
                    "review_dates": ["2026-09-01", "2026-08-15"],
                    "evidence": ["EV1", "EV1"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["exception_rows"]] == ["priority downgrade", "weekend pause"]
    assert plan["review_dates"] == ["2026-08-15", "2026-09-01"]
    assert plan["evidence_references"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_support_sla_exception_plan_reports_required_gaps() -> None:
    plan = generate_design_brief_support_sla_exception_plan({})

    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_escalation_owner",
        "missing_review_date",
        "missing_coverage_rule",
    ]
    assert json.loads(json.dumps(plan)) == plan
