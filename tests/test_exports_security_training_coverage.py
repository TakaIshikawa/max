from __future__ import annotations

import json

from max.exports.security_training_coverage import (
    build_security_training_coverage_report,
    render_security_training_coverage_json,
    render_security_training_coverage_markdown,
)


def test_security_training_coverage_orders_risky_training_before_completed() -> None:
    report = build_security_training_coverage_report(
        [
            {
                "learner": "Ari",
                "team": "Engineering",
                "role": "Developer",
                "campaign": "FY26",
                "training": "Secure coding",
                "completed": True,
                "expiration_date": "2026-12-31",
            },
            {
                "learner": "Bea",
                "team": "Sales",
                "role": "AE",
                "campaign": "FY26",
                "training": "Phishing",
                "completed": False,
                "due_date": "2026-05-01",
                "owner": "sales-ops",
            },
            {
                "learner": "Cy",
                "team": "Support",
                "role": "Admin",
                "campaign": "FY26",
                "training": "Privacy handling",
                "completed": True,
                "expiration_date": "2026-06-05",
            },
        ],
        as_of="2026-05-20",
    )

    assert [row["learner"] for row in report["records"]] == ["Bea", "Cy", "Ari"]
    assert report["summary"]["assigned_count"] == 3
    assert report["summary"]["completed_count"] == 1
    assert report["summary"]["coverage_percent"] == 33.3
    assert report["summary"]["overdue_count"] == 1
    assert report["summary"]["expiring_count"] == 1
    markdown = render_security_training_coverage_markdown(report)
    assert markdown.index("#### Bea - Phishing") < markdown.index("#### Ari - Secure coding")
    assert "- Coverage: 33.3%" in markdown
    assert "- Owner: sales-ops" in markdown


def test_security_training_coverage_groups_by_role_and_normalizes_missing_values() -> None:
    report = build_security_training_coverage_report(
        [
            {"person": "Noor", "role": "Engineer", "status": "incomplete"},
            {"learner": "Lee", "role": "Engineer", "status": "completed"},
        ],
        group_by="role",
    )

    assert report["groups"][0]["name"] == "Engineer"
    assert report["groups"][0]["coverage"]["coverage_percent"] == 50.0
    markdown = render_security_training_coverage_markdown(report)
    assert "Unassigned team" in markdown
    assert "Unassigned campaign" in markdown
    assert json.loads(render_security_training_coverage_json(report))["summary"]["incomplete_count"] == 1


def test_security_training_coverage_renders_empty_state() -> None:
    report = build_security_training_coverage_report([])

    assert report["summary"]["coverage_percent"] == 0.0
    assert "No security training records were supplied." in render_security_training_coverage_markdown(report)
