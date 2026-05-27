from __future__ import annotations

from max.spec.accessibility_remediation_roadmap_plan import generate_accessibility_remediation_roadmap_plan


def test_accessibility_remediation_roadmap_plan_orders_blockers_first() -> None:
    plan = generate_accessibility_remediation_roadmap_plan({"metadata": {"accessibility_remediation_roadmap": {"findings": [{"issue": "minor", "severity": "low"}, {"issue": "keyboard trap", "severity": "blocker"}]}}})

    assert [row["name"] for row in plan["issue_inventory"]] == ["keyboard trap", "minor"]


def test_accessibility_remediation_roadmap_plan_marks_missing_wcag_reference() -> None:
    plan = generate_accessibility_remediation_roadmap_plan({"metadata": {"accessibility_remediation_roadmap": {"findings": [{"issue": "label missing"}]}}})

    assert plan["issue_inventory"][0]["wcag_impact"] == "missing WCAG reference"
    assert plan["evidence_gaps"][0]["name"] == "label missing"


def test_accessibility_remediation_roadmap_plan_deduplicates_flows() -> None:
    plan = generate_accessibility_remediation_roadmap_plan({"metadata": {"accessibility_remediation_roadmap": {"findings": [{"issue": "contrast", "affected_flows": ["checkout", "Checkout", "settings"], "wcag": "1.4.3"}]}}})

    assert plan["issue_inventory"][0]["affected_flows"] == ["checkout", "settings"]


def test_accessibility_remediation_roadmap_plan_includes_verification_sections() -> None:
    plan = generate_accessibility_remediation_roadmap_plan({})

    assert plan["acceptance_checks"]
    assert plan["verification_evidence"]
