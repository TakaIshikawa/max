from __future__ import annotations

import json

from max.spec.tenant_isolation_verification_plan import generate_tenant_isolation_verification_plan


def test_tenant_isolation_verification_plan_summarizes_statuses() -> None:
    report = generate_tenant_isolation_verification_plan(_brief())

    assert report == generate_tenant_isolation_verification_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert report["summary"]["verified_count"] == 1
    assert report["summary"]["partial_count"] == 1
    assert report["summary"]["blocked_count"] == 0
    assert [row["boundary"] for row in report["isolation_boundaries"]] == ["data boundary", "queue boundary"]
    assert report["release_blocking_gaps"] == []


def test_tenant_isolation_verification_plan_flags_release_blocking_gaps() -> None:
    report = generate_tenant_isolation_verification_plan({})

    assert [row["gap"] for row in report["release_blocking_gaps"]] == [
        "missing negative tests",
        "missing owner evidence",
        "missing observability evidence",
    ]
    assert report["summary"]["blocked_count"] >= 3


def _brief() -> dict:
    return {
        "tenant_isolation_verification": {
            "isolation_boundaries": [
                {"boundary": "queue boundary", "status": "partial", "owner": "Platform"},
                {"boundary": "data boundary", "status": "verified", "owner": "Storage"},
            ],
            "verification_checks": [{"check": "cross-tenant query guard"}],
            "negative_tests": [{"test": "tenant A cannot read tenant B"}],
            "shared_resource_risks": [{"resource": "shared queue"}],
            "owners": [{"owner": "Platform"}],
            "evidence_references": ["dash://tenant-isolation"],
        }
    }
