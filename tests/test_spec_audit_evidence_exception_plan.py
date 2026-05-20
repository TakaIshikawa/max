from __future__ import annotations

import json

from max.spec import generate_audit_evidence_exception_plan


def test_audit_evidence_exception_plan_sorts_missing_evidence() -> None:
    plan = generate_audit_evidence_exception_plan(
        _spec(
            "audit_evidence_exception",
            {
                "controls": ["SOC2-CC6.1", "SOC2-CC7.2", "SOC2-CC6.1"],
                "missing_evidence": [
                    {
                        "name": "access review export",
                        "severity": "critical",
                        "review_date": "expired",
                    },
                    {"name": "ticket sample", "severity": "medium", "review_date": "missing"},
                    {"name": "policy attestation", "severity": "high", "review_date": "ready"},
                    {"name": "access review export", "severity": "critical"},
                ],
                "compensating_controls": ["manager attestation"],
                "exception_owners": ["audit owner"],
                "expiration_review_dates": ["2026-06-01"],
                "auditor_communications": ["auditor memo"],
                "validation_checks": ["exception review"],
            },
        )
    )

    assert [item["name"] for item in plan["controls"]] == ["SOC2-CC6.1", "SOC2-CC7.2"]
    assert [item["name"] for item in plan["missing_evidence"]] == [
        "access review export",
        "policy attestation",
        "ticket sample",
    ]
    assert plan["missing_evidence"][0]["review_date"] == "expired"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_audit_evidence_exception_plan_defaults_sparse_input() -> None:
    plan = generate_audit_evidence_exception_plan({})

    assert plan["controls"][0]["name"] == "primary audit control"
    assert plan["missing_evidence"][0]["name"] == "missing audit evidence"
    assert set(plan) >= {
        "compensating_controls",
        "exception_owners",
        "expiration_review_dates",
        "auditor_communications",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
