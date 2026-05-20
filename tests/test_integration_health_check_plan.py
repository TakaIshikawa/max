from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.integration_health_check_plan import generate_integration_health_check_plan, render_integration_health_check_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "int-1"
    unit.title = "ERP Sync"
    unit.domain = "enterprise"
    unit.suggested_stack = {"queue": "SQS"}
    return unit


def test_integration_health_check_extracts_dependencies_from_tact_spec() -> None:
    spec = {"solution": {"suggested_stack": {"api": "Salesforce", "db": "Postgres"}}, "execution": {"dependencies": ["Billing API"]}}
    plan = generate_integration_health_check_plan(_unit(), None, spec)

    assert plan["kind"] == "max.spec.integration_health_check_plan"
    assert [row["name"] for row in plan["dependency_inventory"]][:2] == ["api: Salesforce", "db: Postgres"]
    assert plan["health_checks"][0]["dependency_id"] == "IHC-D1"
    assert plan["launch_gate"]["required_passes"] == len(plan["health_checks"])


def test_integration_health_check_uses_fallback_without_tact_spec() -> None:
    unit = _unit()
    unit.suggested_stack = {}
    plan = generate_integration_health_check_plan(unit)

    assert plan["dependency_inventory"][0]["name"] == "primary customer system"
    assert plan["dependency_inventory"][0]["source"] == "fallback"
    assert plan["recovery_checks"][0]["pass_condition"] == "transaction completes and monitoring clears"


def test_integration_health_check_markdown_renders_sections() -> None:
    markdown = render_integration_health_check_plan_markdown(generate_integration_health_check_plan(_unit()))

    assert "## Dependency Inventory" in markdown
    assert "## Health Checks" in markdown
    assert "## Launch Gate" in markdown
