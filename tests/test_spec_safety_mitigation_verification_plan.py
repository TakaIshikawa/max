from __future__ import annotations

from max.spec.safety_mitigation_verification_plan import (
    generate_safety_mitigation_verification_plan,
)


def test_safety_mitigation_verification_plan_maps_findings_to_mitigations() -> None:
    plan = generate_safety_mitigation_verification_plan(
        {
            "findings": [
                {
                    "finding": "unsafe medical advice",
                    "severity": "critical",
                    "owner": "safety",
                    "mitigations": ["refusal policy update", "retrieval filter"],
                    "verification_steps": ["red-team replay", "human review sample"],
                    "test_evidence": "eval run 42",
                },
                {
                    "finding": "self-harm escalation gap",
                    "severity": "high",
                    "mitigation": "crisis routing prompt",
                },
            ],
            "residual_risk": ["low residual risk after routing monitor"],
            "rollback_criteria": ["critical safety regression"],
            "monitoring_follow_up": ["weekly queue audit"],
            "signoff": ["safety and release approval"],
        }
    )

    assert plan["title"] == "Safety Mitigation Verification Plan"
    assert [item["finding"] for item in plan["mitigation_mapping"]] == [
        "unsafe medical advice",
        "self-harm escalation gap",
    ]
    assert plan["mitigation_mapping"][0]["mitigations"] == "refusal policy update; retrieval filter"
    assert plan["mitigation_mapping"][0]["verification_steps"] == (
        "red-team replay; human review sample"
    )
    assert {blocker["gap"] for blocker in plan["verification_blockers"]} == {
        "missing evidence",
        "missing owner",
    }
    assert plan["residual_risk"][0]["name"] == "low residual risk after routing monitor"
    assert plan["monitoring_follow_up"][0]["name"] == "weekly queue audit"


def test_safety_mitigation_verification_plan_defaults_blockers_and_sections() -> None:
    plan = generate_safety_mitigation_verification_plan({})

    assert plan["schema_version"] == "max.spec.safety_mitigation_verification_plan.v1"
    assert plan["summary"]["finding_count"] == 1
    assert plan["finding_summary"][0]["finding"] == "safety finding"
    assert [blocker["gap"] for blocker in plan["verification_blockers"]] == [
        "missing owner",
        "missing evidence",
    ]
    assert plan["rollback_criteria"][0]["name"] == (
        "critical safety regression, mitigation bypass, monitor breach, or reviewer rejection"
    )
