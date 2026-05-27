from __future__ import annotations

from max.spec.vendor_exit_readiness_plan import generate_vendor_exit_readiness_plan


def test_plan_contains_required_sections_and_flags_critical() -> None:
    markdown = generate_vendor_exit_readiness_plan({"vendors": [{"name": "CorePay", "severity": "critical", "owner": "Mina", "replacement": "Stripe"}]})
    for section in ["Vendor Inventory", "Replacement Options", "Data Export and Verification", "Contract Notice Dates", "Operational Cutover", "Residual Risks", "Owner Checklist"]:
        assert f"## {section}" in markdown
    assert "exit risk High" in markdown


def test_missing_owner_defaults_and_missing_replacement_is_high_risk() -> None:
    markdown = generate_vendor_exit_readiness_plan({"vendors": [{"name": "LogsCo"}]})
    assert "owner Unassigned" in markdown
    assert "No replacement path defined" in markdown
    assert "High risk" in markdown


def test_output_order_is_deterministic() -> None:
    inputs = {"vendors": [{"name": "Zulu"}, {"name": "Alpha"}]}
    first = generate_vendor_exit_readiness_plan(inputs)
    second = generate_vendor_exit_readiness_plan({"vendors": list(reversed(inputs["vendors"]))})
    assert first == second
    assert first.index("Alpha") < first.index("Zulu")
