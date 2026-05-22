from __future__ import annotations

import json

from max.spec import generate_incident_evidence_preservation_plan


def test_incident_evidence_preservation_plan_orders_sources_and_custody() -> None:
    plan = generate_incident_evidence_preservation_plan(
        _spec(
            "incident_evidence_preservation",
            {
                "scope": ["payment incident"],
                "evidence_sources": [
                    {"source": "app logs", "system": "api", "owner": "appsec", "severity": "low"},
                    {"source": "database snapshot", "system": "billing", "owner": "dba", "severity": "high"},
                ],
                "preservation": ["export logs"],
                "retention": ["legal hold"],
                "access_controls": ["least privilege"],
                "custody": ["custody log"],
                "owners": ["legal owner"],
                "integrity": ["hash export"],
                "release": ["legal release"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.incident_evidence_preservation_plan.v1"
    assert [item["name"] for item in plan["evidence_inventory"]] == ["database snapshot", "app logs"]
    assert plan["evidence_inventory"][0]["owner"] == "dba"
    assert set(plan) >= {"preservation_actions", "retention_holds", "access_controls", "custody_log", "integrity_checks", "release_criteria"}
    assert json.loads(json.dumps(plan)) == plan


def test_incident_evidence_preservation_plan_defaults_sparse_input() -> None:
    plan = generate_incident_evidence_preservation_plan({})

    assert plan["evidence_inventory"][0]["owner"] == "security_owner"
    assert plan["integrity_checks"][0]["name"] == "hash, timestamp, and access log verification"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["iep-1"]}}
