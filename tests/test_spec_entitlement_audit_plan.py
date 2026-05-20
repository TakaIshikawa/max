from __future__ import annotations

import json

from max.spec.entitlement_audit_plan import KIND, SCHEMA_VERSION, generate_entitlement_audit_plan


def test_entitlement_audit_plan_flags_critical_mismatch() -> None:
    plan = generate_entitlement_audit_plan(
        {
            "project": {"title": "Admin Console"},
            "evidence": {"signal_ids": ["sig-1"]},
            "metadata": {
                "entitlement_audit": {
                    "entitlement_scope": ["admin roles"],
                    "sampled_accounts": [{"name": "alice", "owner": "IT", "entitlement": "admin"}],
                    "mismatch_findings": [{"name": "stale admin", "severity": "critical", "owner": "IT"}],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["audit_outcome"] == "failed"
    assert plan["remediation_actions"][0]["severity"] == "critical"
    assert plan["sampled_accounts"][0]["evidence_reference_ids"] == ["EV1"]
    json.dumps(plan)


def test_entitlement_audit_plan_defaults_scope_and_attestation() -> None:
    plan = generate_entitlement_audit_plan({})

    assert plan["entitlement_scope"]
    assert plan["owner_attestations"]
    assert plan["audit_outcome"] in {"passed", "conditional"}
