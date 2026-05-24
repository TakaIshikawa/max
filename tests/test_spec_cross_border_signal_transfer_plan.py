from __future__ import annotations

from max.spec import generate_cross_border_signal_transfer_plan


def test_cross_border_signal_transfer_plan_normalizes_aliases_and_evidence() -> None:
    plan = generate_cross_border_signal_transfer_plan(
        {
            "evidence": {"source_idea_ids": ["idea-transfer"]},
            "metadata": {
                "cross_border_signal_transfer": {
                    "flows": [
                        {
                            "signal": "fraud risk score",
                            "origin_region": "EU",
                            "destination_region": "US",
                            "data_class": "pseudonymous behavioral signal",
                        }
                    ],
                    "basis": ["standard contractual clauses"],
                    "safeguards": ["regional encryption boundary"],
                    "approvals": ["privacy and legal approval"],
                    "monitors": ["daily destination region drift check"],
                    "rollback": ["restore eu-only signal routing"],
                }
            },
        }
    )

    assert plan["signal_flows"][0]["name"] == "fraud risk score"
    assert plan["signal_flows"][0]["origin_region"] == "EU"
    assert plan["signal_flows"][0]["destination_region"] == "US"
    assert plan["approval_workflow"][0]["name"] == "privacy and legal approval"
    assert plan["monitoring"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {
        "signal_flows",
        "transfer_basis",
        "safeguards",
        "residency_checks",
        "approval_workflow",
        "monitoring",
        "rollback_plan",
        "evidence_references",
    }


def test_cross_border_signal_transfer_plan_defaults_flow_and_safeguards() -> None:
    plan = generate_cross_border_signal_transfer_plan({})

    assert plan["signal_flows"][0]["name"] == "cross-border signal transfer flow"
    assert plan["safeguards"]
    assert "encryption" in plan["safeguards"][0]["name"]


def test_cross_border_signal_transfer_plan_accepts_regions_alias() -> None:
    plan = generate_cross_border_signal_transfer_plan(
        {
            "metadata": {
                "cross_border_signal_transfer": {
                    "regions": [{"origin_region": "APAC", "destination_region": "EU"}]
                }
            }
        }
    )

    assert plan["signal_flows"][0]["origin_region"] == "APAC"
    assert plan["signal_flows"][0]["destination_region"] == "EU"
