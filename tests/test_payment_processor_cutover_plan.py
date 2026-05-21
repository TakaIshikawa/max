from __future__ import annotations

import json

from max.spec.payment_processor_cutover_plan import (
    KIND,
    generate_payment_processor_cutover_plan,
    render_payment_processor_cutover_plan_markdown,
)


def test_payment_processor_cutover_plan_rich_input_is_deterministic() -> None:
    report = generate_payment_processor_cutover_plan(_brief())

    assert report == generate_payment_processor_cutover_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert [row["name"] for row in report["payment_providers"]] == ["Adyen", "Stripe"]
    assert [row["provider"] for row in report["cutover_steps"]] == ["Adyen", "Stripe"]
    assert [row["check"] for row in report["reconciliation_checks"]] == ["settlement parity", "webhook parity"]
    assert report["rollback_triggers"][0]["criteria"] == "payment auth failures above 1%"
    assert report["owner_assignments"][0]["owner"] == "FinOps"
    assert report["readiness_warnings"] == []


def test_payment_processor_cutover_plan_sparse_input_flags_missing_readiness() -> None:
    report = generate_payment_processor_cutover_plan({})

    assert report["summary"]["readiness"] == "blocked"
    assert [warning["warning"] for warning in report["readiness_warnings"]] == [
        "missing owner assignment",
        "missing reconciliation evidence",
        "missing rollback trigger",
        "missing evidence references",
    ]
    assert json.loads(json.dumps(report)) == report


def test_payment_processor_cutover_plan_markdown_includes_providers_and_rollback_criteria() -> None:
    markdown = render_payment_processor_cutover_plan_markdown(generate_payment_processor_cutover_plan(_brief()))

    assert "## Payment Providers" in markdown
    assert "Adyen" in markdown
    assert "Stripe" in markdown
    assert "## Rollback Criteria" in markdown
    assert "payment auth failures above 1%" in markdown


def _brief() -> dict:
    return {
        "payment_processor_cutover": {
            "providers": [
                {"name": "Stripe", "role": "current", "status": "active"},
                {"name": "Adyen", "role": "target", "status": "ready"},
            ],
            "cutover_steps": [
                {"provider": "Stripe", "step": "drain old auth traffic", "window": "2026-06-01 02:00Z", "sequence": "2"},
                {"provider": "Adyen", "step": "enable new auth traffic", "window": "2026-06-01 01:00Z", "sequence": "1"},
            ],
            "reconciliation_checks": [
                {"provider": "Stripe", "check": "webhook parity", "evidence": "evidence://webhook-parity", "owner": "FinOps"},
                {"provider": "Adyen", "check": "settlement parity", "evidence": "evidence://settlement-parity", "owner": "FinOps"},
            ],
            "rollback_triggers": [
                {"provider": "Adyen", "trigger": "auth failure spike", "criteria": "payment auth failures above 1%", "owner": "Payments lead"},
                {"provider": "Stripe", "trigger": "settlement mismatch", "criteria": "unmatched settlement batch", "owner": "Payments lead"},
            ],
            "owners": [
                {"provider": "Adyen", "role": "reconciliation", "owner": "FinOps"},
                {"provider": "Stripe", "role": "traffic", "owner": "Payments lead"},
            ],
            "evidence_references": ["runbook://payments-cutover", "ticket://PAY-123"],
        }
    }
