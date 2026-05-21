from __future__ import annotations

import json

from max.spec.api_client_migration_readiness_plan import generate_api_client_migration_readiness_plan


def test_api_client_migration_readiness_plan_groups_readiness() -> None:
    report = generate_api_client_migration_readiness_plan(_brief())

    assert report == generate_api_client_migration_readiness_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert [row["cohort"] for row in report["client_cohorts"]] == ["legacy partners", "mobile apps", "server apps"]
    assert report["summary"] == {"ready_count": 1, "at_risk_count": 1, "blocked_count": 1}
    assert [row["blocker"] for row in report["blockers"]] == [
        "expired deadline",
        "missing migration guide",
    ]


def test_api_client_migration_readiness_plan_flags_missing_owner() -> None:
    report = generate_api_client_migration_readiness_plan({"client_cohorts": [{"cohort": "unowned apps"}]})

    assert report["summary"]["blocked_count"] == 1
    assert [row["blocker"] for row in report["blockers"]] == ["missing migration guide", "unassigned owner"]


def _brief() -> dict:
    return {
        "api_client_migration_readiness": {
            "client_cohorts": [
                {"cohort": "server apps", "owner": "API team", "deadline": "2026-07-01", "migration_guide": "guide://server"},
                {"cohort": "mobile apps", "owner": "Mobile team", "deadline": "2026-07-01"},
                {"cohort": "legacy partners", "owner": "Partner team", "deadline": "2026-01-01", "migration_guide": "guide://partner"},
            ],
            "deprecated_endpoints": [{"endpoint": "/v1/payments"}],
            "sdk_requirements": [{"sdk": "python>=3.0"}],
            "migration_guidance": [{"guide": "guide://server"}],
            "deadlines": [{"deadline": "2026-07-01"}],
            "owners": [{"owner": "API team"}],
            "validation_checks": [{"check": "contract tests pass"}],
        }
    }
