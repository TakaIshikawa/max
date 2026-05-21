from __future__ import annotations

import json

from max.spec.data_subprocessor_change_plan import generate_data_subprocessor_change_plan


def test_data_subprocessor_change_plan_normalizes_risk_summary() -> None:
    report = generate_data_subprocessor_change_plan(_brief())

    assert report == generate_data_subprocessor_change_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert [row["name"] for row in report["subprocessors"]] == ["Acme Analytics", "Tokyo Mail"]
    assert report["data_classes"] == ["email", "usage"]
    assert report["regions"] == ["EU", "JP", "US"]
    assert report["summary"]["high_risk_count"] == 0
    assert report["summary"]["notice_blocked_count"] == 0


def test_data_subprocessor_change_plan_flags_notice_dpa_and_region() -> None:
    report = generate_data_subprocessor_change_plan(
        {"subprocessors": [{"name": "Unknown Vendor", "regions": ["Mars"], "data_classes": ["email"]}]}
    )

    assert [row["warning"] for row in report["readiness_warnings"]] == [
        "missing notice date",
        "missing DPA review",
        "unsupported regions",
    ]
    assert report["summary"]["high_risk_count"] == 1
    assert report["summary"]["notice_blocked_count"] == 1


def _brief() -> dict:
    return {
        "data_subprocessor_change": {
            "subprocessors": [
                {"name": "Tokyo Mail", "regions": ["JP"], "data_classes": ["email"], "notice_date": "2026-06-01", "dpa_status": "approved"},
                {"name": "Acme Analytics", "regions": ["US", "EU"], "data_classes": ["usage"], "notice_date": "2026-06-01", "dpa_status": "approved"},
            ],
            "customer_notice_requirements": [{"notice": "standard notice", "date": "2026-06-01"}],
            "dpa_review": [{"item": "DPA addendum", "status": "approved"}],
            "objection_handling": [{"path": "support objection queue"}],
            "rollback_options": [{"option": "disable export"}],
            "evidence_references": ["legal://dpa"],
        }
    }
