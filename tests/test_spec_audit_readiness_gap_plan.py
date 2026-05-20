from __future__ import annotations

import json

from max.spec import generate_audit_readiness_gap_plan as exported_generator
from max.spec.audit_readiness_gap_plan import KIND, SCHEMA_VERSION, generate_audit_readiness_gap_plan


def test_audit_readiness_gap_plan_converts_missing_evidence_to_gaps() -> None:
    plan = generate_audit_readiness_gap_plan(
        {
            "metadata": {
                "audit_readiness_gap": {
                    "controls": ["change control"],
                    "required_evidence": [
                        {"control": "change control", "evidence": "approval ticket", "owner": "pm"},
                        {"control": "access review", "evidence": "review export", "owner": "security"},
                    ],
                    "existing_evidence": ["approval ticket"],
                    "audit_deadline": "2026-06-01",
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["evidence_gap_count"] == 1
    assert plan["evidence_gaps"][0]["missing_evidence"] == "review export"
    assert plan["remediation_actions"][0]["owner"] == "security"
    assert exported_generator({})["kind"] == KIND


def test_audit_readiness_gap_plan_defaults_are_stable_and_json_serializable() -> None:
    first = generate_audit_readiness_gap_plan({})
    second = generate_audit_readiness_gap_plan({})

    assert first == second
    assert first["required_evidence"]
    assert first["evidence_gaps"]
    assert json.loads(json.dumps(first))["kind"] == KIND
