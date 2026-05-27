from __future__ import annotations

import json

from max.spec.model_access_deprovisioning_plan import generate_model_access_deprovisioning_plan


def test_model_access_deprovisioning_plan_flags_lingering_access() -> None:
    plan = generate_model_access_deprovisioning_plan(
        _spec(
            "model_access_deprovisioning",
            {
                "access_subjects": [
                    {"user": "alice", "access": "active", "provider": "llm-a"},
                    {"service": "worker", "access": "active", "exception_id": "EX-1"},
                ],
                "exceptions": [{"service": "worker", "owner": "risk", "expiry": "2026-06-01"}],
            },
        )
    )

    assert [item["name"] for item in plan["access_subjects"]] == ["alice", "worker"]
    assert [item["name"] for item in plan["blockers"]] == ["alice lingering access"]
    assert plan["exception_handling"][0]["expiry"] == "2026-06-01"


def test_model_access_deprovisioning_plan_preserves_metadata_and_is_deterministic() -> None:
    payload = _spec("model_access_deprovisioning", {"revocations": ["disable provider key"]})

    first = generate_model_access_deprovisioning_plan(payload)

    assert first == generate_model_access_deprovisioning_plan(payload)
    assert json.loads(json.dumps(first)) == first
    assert first["source"]["idea_id"] == "idea-1"
    assert first["revocation_tasks"][0]["name"] == "disable provider key"
    assert first["audit_validation"][0]["name"] == "audit log confirms revocation, key disablement, and denied access attempts"


def _spec(key: str, hints: dict) -> dict:
    return {"source": {"idea_id": "idea-1"}, "metadata": {key: hints}, "evidence": {"signal_ids": ["sig-1"]}}
