from __future__ import annotations

from max.api import design_brief_technical_risks_to_json


def test_design_brief_technical_risks_renderer_groups_risks() -> None:
    payload = design_brief_technical_risks_to_json(
        {
            "schema_version": "max.design_brief.technical_risks.v1",
            "kind": "max.design_brief.technical_risks",
            "design_brief": {"id": "brief-1", "title": "Risky Brief"},
            "summary": {"risk_count": 2, "high_risk_count": 1},
            "technical_risks": [
                {
                    "id": "RISK-01",
                    "category": "integration",
                    "severity": "high",
                    "likelihood": "medium",
                    "description": "API instability",
                    "mitigation_strategy": "Add contract tests",
                    "owner": "engineering_lead",
                },
                {
                    "id": "RISK-02",
                    "category": "security",
                    "severity": "medium",
                    "likelihood": "low",
                    "description": "Permission drift",
                    "mitigation_strategy": "Review scopes",
                    "owner": "security_lead",
                },
            ],
        }
    )

    assert payload["kind"] == "max.api.design_brief_technical_risks"
    assert payload["summary"]["risk_count"] == 2
    assert {row["category"] for row in payload["risk_categories"]} == {
        "integration",
        "security",
    }
    assert {row["severity"] for row in payload["severity_levels"]} == {
        "high",
        "medium",
    }
    assert payload["mitigation_strategies"][0]["strategy"] == "Add contract tests"
    assert payload["impact_assessments"][0]["description"] == "API instability"
