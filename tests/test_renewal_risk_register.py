from __future__ import annotations

import json

from max.exports.renewal_risk_register import export_renewal_risk_register, render_renewal_risk_register_json


def test_renewal_risk_register_classifies_and_sorts_risk() -> None:
    rows = export_renewal_risk_register(
        [
            {"account_name": "Beta", "renewal_date": "2026-08-01", "arr": 100000, "health": ["green"], "commercial_signal": "expansion"},
            {"account_name": "Acme", "renewal_date": "2026-01-20", "arr": "250000", "health_indicators": ["red usage"], "open_incidents": ["sev1"], "open_blockers": ["security review"], "contraction_signal": "budget cut"},
        ],
        as_of="2026-01-01",
    )

    assert [row["account_name"] for row in rows] == ["Acme", "Beta"]
    assert rows[0]["severity"] == "critical"
    assert rows[1]["severity"] == "low"
    assert "Open incidents: 1" in rows[0]["risk_drivers"]


def test_renewal_risk_register_defaults_missing_optional_fields() -> None:
    rows = export_renewal_risk_register([{}])

    assert rows == [
        {
            "account_name": "Unknown",
            "renewal_date": "",
            "days_to_renewal": None,
            "arr": 0.0,
            "contract_value": 0.0,
            "health_indicators": ["unknown"],
            "risk_drivers": ["No active renewal risk drivers"],
            "mitigation_owner": "Unassigned",
            "next_action": "Maintain standard renewal monitoring.",
            "severity": "low",
        }
    ]


def test_renewal_risk_register_output_is_json_serializable_and_stable() -> None:
    records = [
        {"account_name": "Zulu", "renewal_date": "2026-03-01"},
        {"account_name": "Alpha", "renewal_date": "2026-03-01"},
    ]

    assert export_renewal_risk_register(records) == export_renewal_risk_register(records)
    assert [row["account_name"] for row in export_renewal_risk_register(records)] == ["Alpha", "Zulu"]
    assert json.loads(render_renewal_risk_register_json(export_renewal_risk_register(records)))
