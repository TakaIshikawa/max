from __future__ import annotations

import json

from max.spec.prompt_secret_rotation_plan import generate_prompt_secret_rotation_plan


def test_prompt_secret_rotation_plan_flags_exposed_secret_blockers() -> None:
    plan = generate_prompt_secret_rotation_plan(
        _spec(
            "prompt_secret_rotation",
            {
                "affected_assets": [
                    {"prompt": "billing prompt", "exposure": "exposed", "secret_type": "api key"},
                ],
                "validation": ["scanner clean"],
            },
        )
    )

    assert plan["affected_assets"][0]["name"] == "billing prompt"
    assert {item["name"] for item in plan["blockers"]} == {
        "billing prompt missing owner",
        "billing prompt missing validation evidence",
    }
    assert plan["validation_checklist"][0]["name"] == "scanner clean"


def test_prompt_secret_rotation_plan_preserves_metadata_and_is_deterministic() -> None:
    payload = _spec(
        "prompt_secret_rotation",
        {"affected_assets": [{"tool": "search connector", "owner": "sec", "exposure": "contained", "validation_evidence": "run-1"}]},
    )

    first = generate_prompt_secret_rotation_plan(payload)
    second = generate_prompt_secret_rotation_plan(payload)

    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["source"]["idea_id"] == "idea-1"
    assert first["evidence_references"][0]["reference"] == "signal:sig-1"
    assert first["blockers"] == []


def _spec(key: str, hints: dict) -> dict:
    return {"source": {"idea_id": "idea-1"}, "metadata": {key: hints}, "evidence": {"signal_ids": ["sig-1"]}}
