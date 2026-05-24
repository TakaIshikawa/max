from __future__ import annotations

import json

from max.spec import generate_prompt_injection_incident_response_plan


def test_prompt_injection_incident_response_plan_preserves_affected_scope() -> None:
    plan = generate_prompt_injection_incident_response_plan(
        _spec(
            {
                "detection_summary": [{"name": "malicious instruction in source payload", "severity": "high"}],
                "affected_sources": [
                    {"source_id": "sig-2", "owner": "research_owner", "adapter": "rss"},
                    {"source_id": "sig-1", "owner": "source_owner"},
                ],
                "affected_prompts": [
                    {"prompt_id": "prompt-b", "owner": "prompt_owner", "spec_id": "spec-9"},
                    {"prompt_id": "prompt-a", "owner": "safety_owner"},
                ],
                "reviewer_roles": [{"role": "security reviewer", "owner": "secops"}],
                "containment_tasks": ["pause generated spec publication"],
                "evidence_handling": ["snapshot raw source and generated spec"],
                "recovery_steps": ["regenerate clean spec"],
                "communications": ["notify source and prompt owners"],
                "closure_criteria": ["all affected prompts reviewed"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.prompt_injection_incident_response_plan.v1"
    assert [item["source_id"] for item in plan["affected_sources"]] == ["sig-1", "sig-2"]
    assert [item["prompt_id"] for item in plan["affected_prompts"]] == ["prompt-a", "prompt-b"]
    assert plan["affected_sources"][1]["owner"] == "research_owner"
    assert plan["affected_prompts"][0]["owner"] == "safety_owner"
    assert plan["reviewer_roles"][0]["role"] == "security reviewer"
    assert plan["containment_tasks"][0]["name"] == "pause generated spec publication"
    assert plan["evidence_handling"][0]["name"] == "snapshot raw source and generated spec"
    assert json.loads(json.dumps(plan)) == plan


def test_prompt_injection_incident_response_plan_defaults_missing_optional_inputs() -> None:
    plan = generate_prompt_injection_incident_response_plan({})

    assert plan["summary"]["affected_source_count"] == 1
    assert plan["affected_sources"][0]["source_id"] == "unknown_source"
    assert plan["affected_prompts"][0]["prompt_id"] == "unknown_prompt"
    assert set(plan) >= {
        "detection_summary",
        "containment_tasks",
        "evidence_handling",
        "recovery_steps",
        "communications",
        "closure_criteria",
    }


def test_prompt_injection_incident_response_plan_has_deterministic_acceptance_criteria() -> None:
    payload = _spec(
        {
            "source_ids": [{"source_id": "z"}, {"source_id": "a"}],
            "prompt_ids": [{"prompt_id": "p2"}, {"prompt_id": "p1"}],
            "acceptance_criteria": ["clean regenerated specs approved"],
        }
    )

    first = generate_prompt_injection_incident_response_plan(payload)
    second = generate_prompt_injection_incident_response_plan(payload)

    assert first == second
    assert [item["source_id"] for item in first["affected_sources"]] == ["a", "z"]
    assert [item["prompt_id"] for item in first["affected_prompts"]] == ["p1", "p2"]
    assert first["closure_criteria"][0]["name"] == "clean regenerated specs approved"


def _spec(hints: dict) -> dict:
    return {
        "metadata": {"prompt_injection_incident_response": hints},
        "evidence": {"signal_ids": ["pi-1"]},
    }
