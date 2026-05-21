from __future__ import annotations

import json

from max.spec.customer_consent_migration_plan import generate_customer_consent_migration_plan


def test_customer_consent_migration_plan_rich_input() -> None:
    report = generate_customer_consent_migration_plan(_brief())

    assert report == generate_customer_consent_migration_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert [row["category"] for row in report["consent_categories"]] == ["analytics", "marketing"]
    assert [row["cohort"] for row in report["impacted_cohorts"]] == ["EU accounts", "US accounts"]
    assert report["legal_review"]["status"] == "approved"
    assert report["readiness_warnings"] == []


def test_customer_consent_migration_plan_flags_required_warnings() -> None:
    report = generate_customer_consent_migration_plan({})

    assert [row["warning"] for row in report["readiness_warnings"]] == [
        "missing legal approval",
        "missing customer communication",
        "unverified opt-out handling",
        "missing verification evidence",
    ]
    assert report["summary"]["readiness"] == "blocked"


def _brief() -> dict:
    return {
        "customer_consent_migration": {
            "consent_categories": [{"category": "marketing"}, {"category": "analytics"}],
            "impacted_cohorts": [{"cohort": "US accounts"}, {"cohort": "EU accounts"}],
            "migration_rules": [{"rule": "copy explicit opt-in only"}],
            "legal_review": "approved",
            "communications": [{"channel": "email", "cohort": "EU accounts"}],
            "fallback_paths": [{"path": "restore opt-out", "opt_out_verified": "true"}],
            "verification_checks": [{"check": "audit migrated consents", "evidence": "evidence://consent-audit"}],
            "evidence_references": ["legal://approval"],
        }
    }
