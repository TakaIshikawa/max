from __future__ import annotations

import json

from max.spec import generate_operational_ownership_transfer_plan


def test_operational_ownership_transfer_plan_uses_hints() -> None:
    plan = generate_operational_ownership_transfer_plan(
        _spec(
            {
                "source_team": "platform",
                "receiving_team": "sre",
                "owned_services": ["billing api"],
                "responsibility_matrix": [{"name": "paging", "owner": "sre"}],
                "knowledge_transfer_sessions": ["dashboard review"],
                "runbook_updates": ["pager rotation"],
                "support_windows": ["week one"],
                "acceptance_criteria": ["alerts owned"],
                "validation_checks": ["access check"],
            }
        )
    )

    assert plan["ownership_scope"]["source_team"] == "platform"
    assert plan["ownership_scope"]["receiving_team"] == "sre"
    assert plan["responsibility_matrix"][0]["owner"] == "sre"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_operational_ownership_transfer_plan_defaults_sparse_input() -> None:
    plan = generate_operational_ownership_transfer_plan({})

    assert plan["ownership_scope"]["receiving_team"] == "receiving operations team"
    assert plan["ownership_scope"]["owned_services"] == ["primary workflow"]
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"operational_ownership_transfer": hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
