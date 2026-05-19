from __future__ import annotations

import json

from max.spec.customer_health_review_plan import (
    SCHEMA_VERSION,
    generate_customer_health_review_plan,
    render_customer_health_review_plan_markdown,
)


def _spec() -> dict:
    return {
        "title": "Enterprise Customer Health Review",
        "customer_segments": [
            {"segment": "Strategic Accounts", "owner": "Ava"},
            {"segment": "Growth Accounts", "owner": "Ben"},
            {"segment": "Startup Accounts", "owner": "Cy"},
        ],
        "health_signals": {
            "Strategic Accounts": {"score": 42},
            "Growth Accounts": {"score": 68},
            "Startup Accounts": {"score": 88},
        },
        "risk_drivers": {
            "Strategic Accounts": ["renewal risk", "blocked integration"],
            "Growth Accounts": ["low adoption"],
            "Startup Accounts": [],
        },
        "review_owners": {"Strategic Accounts": "Ava", "Growth Accounts": "Ben", "Startup Accounts": "Cy"},
        "intervention_actions": {
            "critical": "Open executive save plan.",
            "watch": "Schedule adoption workshop.",
            "healthy": "Review expansion signal.",
        },
        "review_cadence": {
            "cadence": "biweekly",
            "anchor_date": "2026-05-01",
            "owner": "Customer Success Ops",
            "meeting_format": "segment review",
        },
    }


def test_customer_health_review_returns_structured_rows() -> None:
    first = generate_customer_health_review_plan(_spec())
    second = generate_customer_health_review_plan(_spec())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.customer_health_review_plan"
    assert json.loads(json.dumps(first))["summary"]["title"] == "Enterprise Customer Health Review"
    assert first["customer_health_rows"][0] == {
        "id": "CHR1",
        "segment": "Strategic Accounts",
        "score": 42.0,
        "risk_state": "critical",
        "risk_drivers": ["renewal risk", "blocked integration"],
        "owner": "Ava",
        "intervention": "Open executive save plan.",
        "next_review_date": "2026-05-08",
    }
    assert len(first["intervention_plan"]) == 3


def test_customer_health_review_classifies_risk_and_sorts_lowest_health_first() -> None:
    plan = generate_customer_health_review_plan(_spec())

    assert [(row["segment"], row["score"], row["risk_state"]) for row in plan["customer_health_rows"]] == [
        ("Strategic Accounts", 42.0, "critical"),
        ("Growth Accounts", 68.0, "watch"),
        ("Startup Accounts", 88.0, "healthy"),
    ]
    assert [row["segment"] for row in plan["at_risk_accounts"]] == ["Strategic Accounts", "Growth Accounts"]
    assert plan["summary"]["critical_count"] == 1
    assert plan["summary"]["watch_count"] == 1
    assert plan["summary"]["healthy_count"] == 1


def test_customer_health_review_markdown_is_deterministic() -> None:
    plan = generate_customer_health_review_plan(_spec())

    first = render_customer_health_review_plan_markdown(plan)
    second = render_customer_health_review_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Enterprise Customer Health Review Customer Health Review Plan")
    assert "## Health Summary" in first
    assert "### CHR1: Strategic Accounts" in first
    assert "- Risk drivers: renewal risk, blocked integration" in first
    assert "## At-Risk Accounts" in first
    assert "## Intervention Plan" in first
    assert "Open executive save plan." in first
    assert "## Review Cadence" in first
    assert "- Cadence: biweekly" in first
