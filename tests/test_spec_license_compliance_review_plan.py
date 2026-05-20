from __future__ import annotations

from max.spec import generate_license_compliance_review_plan, render_license_compliance_review_plan_markdown


def test_license_compliance_review_plan_classifies_license_statuses() -> None:
    plan = generate_license_compliance_review_plan(
        {
            "policy": {"allowed": ["MIT"], "denied": ["AGPL-3.0"], "review_required": ["MPL-2.0"]},
            "components": [
                {"component": "ok-lib", "license": "MIT", "owner": "app"},
                {"component": "review-lib", "license": "MPL-2.0"},
                {"component": "bad-lib", "license": "AGPL-3.0"},
                {"component": "unknown-lib"},
            ],
        }
    )

    assert plan["schema_version"] == "max-license-compliance-review-plan/v1"
    assert [row["component"] for row in plan["component_rows"]] == ["bad-lib", "unknown-lib", "review-lib", "ok-lib"]
    assert [row["id"] for row in plan["component_rows"]] == ["LCR-001", "LCR-002", "LCR-003", "LCR-004"]
    assert plan["summary"] == {"component_count": 4, "denied_count": 1, "review_required_count": 2, "allowed_count": 1}
    assert plan["policy_violations"][0]["component"] == "bad-lib"
    assert plan["approval_queue"][0]["component"] == "unknown-lib"
    assert plan["remediation_actions"][0]["action"] == "replace component or obtain legal exception"


def test_license_compliance_review_markdown_sections_are_deterministic() -> None:
    payload = {"components": [{"component": "z", "license": "MIT"}, {"component": "a", "license": "MIT"}]}

    first = render_license_compliance_review_plan_markdown(payload)
    second = render_license_compliance_review_plan_markdown(payload)

    assert first == second
    assert first.index("LCR-001: a") < first.index("LCR-002: z")
    for heading in ["## Component Review", "## Policy Violations", "## Approval Queue", "## Remediation Actions"]:
        assert heading in first
