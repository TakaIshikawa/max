from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.security_exception_review_plan import generate_security_exception_review_plan, render_security_exception_review_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "sec-1"
    unit.title = "Temporary Access Exception"
    unit.domain = "security"
    unit.solution = "temporary admin access"
    unit.domain_risks = ["access control exception", "privacy review"]
    return unit


def _evaluation() -> MagicMock:
    evaluation = MagicMock()
    evaluation.overall_score = 45
    evaluation.weaknesses = ["encryption evidence missing"]
    return evaluation


def test_security_exception_risk_heavy_units_produce_high_severity_rows() -> None:
    plan = generate_security_exception_review_plan(_unit(), _evaluation())

    assert plan["kind"] == "max.spec.security_exception_review_plan"
    assert plan["affected_controls"][0]["severity"] == "high"
    assert any(role["role"] == "risk committee" for role in plan["approval_roles"])
    assert plan["expiry_criteria"][0]["criteria"] == "exception expires after 30 days"


def test_security_exception_markdown_renders_review_sections() -> None:
    markdown = render_security_exception_review_plan_markdown(generate_security_exception_review_plan(_unit(), _evaluation()))

    assert "## Exception Scope" in markdown
    assert "## Affected Controls" in markdown
    assert "risk committee" in markdown
