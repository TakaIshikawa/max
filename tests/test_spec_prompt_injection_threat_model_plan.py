from __future__ import annotations

import json

from max.spec.prompt_injection_threat_model_plan import (
    KIND,
    generate_prompt_injection_threat_model_plan,
)


def test_prompt_injection_threat_model_plan_populates_complete_inputs() -> None:
    plan = generate_prompt_injection_threat_model_plan(
        {
            "project": {"title": "RAG assistant"},
            "metadata": {
                "prompt_injection_threat_model": {
                    "entry_points": [{"surface": "support article retrieval", "owner": "search_owner"}],
                    "trust_boundaries": [{"name": "retrieval content to model context", "trust_level": "untrusted"}],
                    "attack_scenarios": [{"scenario": "malicious article overrides system prompt", "entry_point": "support article retrieval"}],
                    "mitigations": [{"control": "quote retrieved content and require tool authorization", "coverage": "retrieval"}],
                    "detection_checks": [{"name": "tool call anomaly alert", "threshold": "5 per minute"}],
                    "residual_risks": [{"name": "novel jailbreak phrasing", "accepted_by": "security_lead"}],
                }
            },
            "evidence": {"signal_ids": ["rag-threat-review"]},
        }
    )

    assert plan["kind"] == KIND
    assert plan["summary"]["attack_scenario_count"] == 1
    assert plan["entry_points"][0]["name"] == "support article retrieval"
    assert plan["attack_scenarios"][0]["entry_point"] == "support article retrieval"
    assert plan["mitigations"][0]["coverage"] == "retrieval"
    assert plan["detection_checks"][0]["threshold"] == "5 per minute"
    assert plan["residual_risks"][0]["accepted_by"] == "security_lead"
    assert plan["blockers"] == []
    assert plan["evidence_references"][0]["reference"] == "signal:rag-threat-review"


def test_prompt_injection_threat_model_plan_blocks_missing_entry_points_or_mitigations() -> None:
    plan = generate_prompt_injection_threat_model_plan({})

    assert [item["name"] for item in plan["blockers"]] == [
        "missing prompt injection entry points",
        "missing prompt injection mitigations",
    ]
    assert plan["summary"]["blocker_count"] == 2
    assert plan["attack_scenarios"][0]["name"] == "indirect prompt injection"


def test_prompt_injection_threat_model_plan_is_deterministic_and_json_serializable() -> None:
    payload = {
        "metadata": {
            "prompt_injection_threat_model": {
                "entry_points": ["chat input"],
                "mitigations": ["instruction hierarchy"],
            }
        }
    }

    first = generate_prompt_injection_threat_model_plan(payload)
    second = generate_prompt_injection_threat_model_plan(payload)

    assert first == second
    assert json.loads(json.dumps(first)) == first
