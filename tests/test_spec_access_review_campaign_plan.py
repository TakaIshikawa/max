from __future__ import annotations

from max.spec.access_review_campaign_plan import generate_access_review_campaign_plan


def test_access_review_campaign_plan_prioritizes_overdue_reviews() -> None:
    markdown = generate_access_review_campaign_plan(
        {
            "project": {"title": "Q2 SOX Review"},
            "metadata": {
                "access_review_campaign": {
                    "systems": [
                        {"system": "wiki", "reviewer": "ops_manager", "risk": "low", "status": "on-track"},
                        {
                            "system": "billing-admin",
                            "reviewer": "finance_controller",
                            "population": ["privileged users"],
                            "risk": "high",
                            "overdue": True,
                            "due_date": "2026-05-01",
                        },
                    ]
                }
            },
        }
    )

    assert markdown.startswith("# Q2 SOX Review Access Review Campaign Plan")
    assert markdown.index("### billing-admin") < markdown.index("### wiki")
    assert "- Overdue assignments: 1" in markdown
    assert "- billing-admin: reviewer > system_owner > security_owner > executive_sponsor." in markdown
    assert "- billing-admin: disable unreviewed privileged access" in markdown


def test_access_review_campaign_plan_renders_clean_on_track_review() -> None:
    markdown = generate_access_review_campaign_plan(
        {
            "reviews": [
                {
                    "system": "support-console",
                    "reviewer": "support_lead",
                    "population": ["support agents"],
                    "risk": "medium",
                    "status": "on-track",
                    "due_date": "2026-06-15",
                    "evidence": "store signed reviewer attestation",
                }
            ]
        }
    )

    assert "## Campaign Summary" in markdown
    assert "## Review Scope" in markdown
    assert "## Reviewer Assignments" in markdown
    assert "## Escalation Schedule" in markdown
    assert "## Remediation Queue" in markdown
    assert "## Evidence Capture" in markdown
    assert "- Status: on-track" in markdown
    assert "- support-console: store signed reviewer attestation" in markdown


def test_access_review_campaign_plan_groups_duplicate_system_reviewer_entries() -> None:
    payload = {
        "metadata": {
            "access_reviews": [
                {
                    "system": "data-warehouse",
                    "reviewer": "data_owner",
                    "population": ["analysts"],
                    "remediation": ["remove dormant accounts"],
                },
                {
                    "system": "data-warehouse",
                    "reviewer": "data_owner",
                    "population": ["admins", "analysts"],
                    "due_date": "2026-06-01",
                },
            ]
        }
    }

    first = generate_access_review_campaign_plan(payload)
    second = generate_access_review_campaign_plan(payload)

    assert first == second
    assert first.count("### data-warehouse") == 1
    assert "- Population: admins, analysts" in first
    assert "- Due date: 2026-06-01" in first
    assert "- Reviewer count: 1" in first
