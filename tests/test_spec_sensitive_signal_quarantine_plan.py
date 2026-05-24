from __future__ import annotations

from max.spec.sensitive_signal_quarantine_plan import (
    KIND,
    generate_sensitive_signal_quarantine_plan,
)


def test_sensitive_signal_quarantine_plan_preserves_custom_categories() -> None:
    plan = generate_sensitive_signal_quarantine_plan(
        {
            "id": "spec-1",
            "metadata": {
                "sensitive_signal_quarantine": {
                    "categories": [
                        {
                            "category": "credential leak",
                            "source": "support transcripts",
                            "severity": "critical",
                            "owner": "security_review",
                            "retention": "7 days",
                        }
                    ],
                    "detection_triggers": ["secret scanner match"],
                    "isolation_controls": ["block downstream indexing"],
                    "reviewer_workflow": ["security review within 24 hours"],
                    "purge_release_criteria": ["purge raw transcript after credential rotation"],
                    "audit_logging": ["record reviewer and purge decision"],
                    "notification_plan": ["notify security owner"],
                }
            },
            "evidence": {"insight_ids": ["sig-1"]},
        }
    )

    assert plan["kind"] == KIND
    assert plan["summary"]["quarantined_signal_category_count"] == 1
    category = plan["quarantined_signal_categories"][0]
    assert category["name"] == "credential leak"
    assert category["source"] == "support transcripts"
    assert category["category"] == "credential leak"
    assert category["severity"] == "critical"
    assert category["owner"] == "security_review"
    assert category["retention"] == "7 days"
    assert plan["detection_triggers"][0]["name"] == "secret scanner match"
    assert plan["isolation_controls"][0]["name"] == "block downstream indexing"
    assert plan["reviewer_workflow"][0]["name"] == "security review within 24 hours"
    assert plan["purge_release_criteria"][0]["name"] == "purge raw transcript after credential rotation"
    assert plan["audit_logging"][0]["name"] == "record reviewer and purge decision"
    assert plan["notification_plan"][0]["name"] == "notify security owner"
    assert plan["evidence_references"][0]["reference"] == "insight:sig-1"


def test_sensitive_signal_quarantine_plan_defaults_are_deterministic() -> None:
    plan = generate_sensitive_signal_quarantine_plan({})

    assert set(plan) >= {
        "schema_version",
        "kind",
        "source",
        "summary",
        "quarantined_signal_categories",
        "detection_triggers",
        "isolation_controls",
        "reviewer_workflow",
        "purge_release_criteria",
        "audit_logging",
        "notification_plan",
        "evidence_references",
    }
    assert plan["quarantined_signal_categories"][0]["name"] == "sensitive signal category pending reviewer disposition"
    assert plan["detection_triggers"][0]["name"] == "PII, credential, health, financial, or customer-confidential signal trigger"
    assert plan["purge_release_criteria"][0]["name"] == "purge sensitive payloads or release only after approved redaction"
