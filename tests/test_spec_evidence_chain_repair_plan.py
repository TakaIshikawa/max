from __future__ import annotations

from max.spec import generate_evidence_chain_repair_plan
from max.spec.evidence_chain_repair_plan import KIND, SCHEMA_VERSION


def test_evidence_chain_repair_plan_complete_inventory_severity_and_sections() -> None:
    plan = generate_evidence_chain_repair_plan(
        {
            "metadata": {
                "evidence_chain_repair": {
                    "broken_chains": [
                        {"id": "b2", "missing_link_type": "evaluation_to_spec", "from_type": "evaluation", "from_id": "eval-1", "affected_specs": ["spec-1", "spec-2", "spec-3"]},
                        {"id": "b1", "missing_link_type": "root_signal", "from_type": "insight", "from_id": "ins-1", "affected_specs": ["spec-1"], "missing_root_signal": True},
                    ]
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["severity"] == "high"
    assert plan["summary"]["affected_spec_count"] == 3
    assert plan["summary"]["missing_root_signal_count"] == 1
    assert [strategy["missing_link_type"] for strategy in plan["repair_strategies"]] == ["evaluation_to_spec", "root_signal"]
    assert plan["validation_queries"][0]["name"] == "missing_upstream_references"
    assert plan["acceptance_metrics"][3]["target"] == "100%"


def test_evidence_chain_repair_plan_partial_inventory_defaults_link_type() -> None:
    plan = generate_evidence_chain_repair_plan(
        {"broken_chains": [{"from_type": "signal", "from_id": "sig-1", "to_type": "insight", "to_id": "missing", "affected_spec_count": 1}]}
    )

    assert plan["summary"]["severity"] == "medium"
    assert plan["broken_chain_inventory"][0]["missing_link_type"] == "signal_to_insight"
    assert plan["repair_strategies"][0]["owner"] == "research_owner"


def test_evidence_chain_repair_plan_empty_inventory_still_validates() -> None:
    plan = generate_evidence_chain_repair_plan({})

    assert plan["summary"]["broken_link_count"] == 0
    assert plan["summary"]["severity"] == "low"
    assert plan["repair_strategies"][0]["missing_link_type"] == "no_broken_links"
    assert any(item["type"] == "empty_inventory_review" for item in plan["detection_inputs"])
