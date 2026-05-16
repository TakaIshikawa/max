from __future__ import annotations

import json

from max.exports.partner_integration_risk_register import (
    export_partner_integration_risk_register,
    render_partner_integration_risk_register_json,
)


def test_partner_integration_risk_register_classifies_exposure_and_preserves_evidence() -> None:
    rows = export_partner_integration_risk_register(
        [
            {"partner": "Okta", "integration_area": "SSO", "customer_exposure": 2, "dependency_health": "healthy"},
            {"partner": "Stripe", "integration_area": "Billing", "customers": ["a", "b", "c"], "dependency_health": "blocked", "api_risk": "critical outage", "evidence_ids": ["inc-1"]},
        ]
    )

    assert [row["partner"] for row in rows] == ["Stripe", "Okta"]
    assert rows[0]["severity"] == "critical"
    assert rows[0]["customer_exposure"] == 3
    assert rows[0]["evidence"] == ["inc-1"]


def test_partner_integration_risk_register_defaults_and_stable_json() -> None:
    rows = export_partner_integration_risk_register([{}, {"partner_name": "Acme", "area": "CRM"}])

    assert rows[0]["partner"] == "Acme"
    assert rows[1]["partner"] == "Unknown"
    assert rows[1]["risk_drivers"] == ["No active partner integration risk drivers"]
    assert json.loads(render_partner_integration_risk_register_json(rows))
