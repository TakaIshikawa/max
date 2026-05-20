from __future__ import annotations

import json

from max.exports.tact_delivery_readiness import (
    KIND,
    SCHEMA_VERSION,
    build_tact_delivery_readiness_report,
    render_tact_delivery_readiness_json,
    render_tact_delivery_readiness_markdown,
)


def test_tact_delivery_readiness_evaluates_required_fields_and_blocked_reason() -> None:
    report = build_tact_delivery_readiness_report(
        [
            {
                "idea_id": "checkout",
                "name": "Fast checkout",
                "profile": "growth",
                "has_spec": True,
                "has_acceptance_criteria": True,
                "has_evidence_trace": True,
                "has_owner": True,
                "has_budget": True,
                "has_risk_notes": True,
                "priority": "high",
            },
            {
                "idea_id": "pricing",
                "profile": "enterprise",
                "has_spec": True,
                "has_acceptance_criteria": True,
                "has_evidence_trace": True,
                "has_owner": True,
                "has_budget": True,
                "has_risk_notes": True,
                "blocked_reason": "legal review",
                "priority": "critical",
            },
        ]
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "item_count": 2,
        "ready_count": 1,
        "blocked_count": 1,
        "readiness_rate": 50.0,
    }
    assert report["ready_items"][0]["idea_id"] == "checkout"
    assert report["blocked_items"][0]["blocked_reason"] == "legal review"


def test_tact_delivery_readiness_aggregates_missing_fields_for_blocked_items() -> None:
    report = build_tact_delivery_readiness_report(
        [
            {"idea_id": "a", "has_spec": True, "has_acceptance_criteria": False, "has_evidence_trace": False, "has_owner": True, "has_budget": False, "has_risk_notes": True},
            {"idea_id": "b", "has_spec": True, "has_acceptance_criteria": False, "has_evidence_trace": True, "has_owner": False, "has_budget": False, "has_risk_notes": False},
        ]
    )

    assert report["missing_field_frequencies"] == [
        {"field": "has_acceptance_criteria", "count": 2},
        {"field": "has_budget", "count": 2},
        {"field": "has_evidence_trace", "count": 1},
        {"field": "has_owner", "count": 1},
        {"field": "has_risk_notes", "count": 1},
    ]


def test_tact_delivery_readiness_sorts_ready_and_blocked_by_priority_then_idea_id() -> None:
    rows = [
        _ready("b", "low"),
        _ready("a", "high"),
        _ready("c", "high"),
        {**_ready("z", "critical"), "has_budget": False},
        {**_ready("y", "high"), "has_owner": False},
    ]

    report = build_tact_delivery_readiness_report(rows)

    assert [row["idea_id"] for row in report["ready_items"]] == ["a", "c", "b"]
    assert [row["idea_id"] for row in report["blocked_items"]] == ["z", "y"]
    assert [row["idea_id"] for row in report["records"]] == ["z", "a", "c", "y", "b"]


def test_tact_delivery_readiness_normalizes_missing_rows_and_renders() -> None:
    report = build_tact_delivery_readiness_report([{"name": "Unowned idea"}])

    assert report["blocked_items"][0]["idea_id"] == "Unowned idea"
    assert report["blocked_items"][0]["priority"] == "unspecified"
    assert report["blocked_items"][0]["missing_fields"] == [
        "has_spec",
        "has_acceptance_criteria",
        "has_evidence_trace",
        "has_owner",
        "has_budget",
        "has_risk_notes",
    ]

    markdown = render_tact_delivery_readiness_markdown(report)
    assert "- Items: 1" in markdown
    assert "## Blocked Items" in markdown
    assert "- No tact-ready items were supplied." in markdown

    rendered = render_tact_delivery_readiness_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered) == report
    assert rendered.splitlines()[1].startswith('  "blocked_items"')


def test_tact_delivery_readiness_empty_input_is_deterministic() -> None:
    report = build_tact_delivery_readiness_report([])

    assert report["summary"] == {
        "item_count": 0,
        "ready_count": 0,
        "blocked_count": 0,
        "readiness_rate": 0.0,
    }
    assert report["missing_field_frequencies"] == []
    assert report["ready_items"] == []
    assert report["blocked_items"] == []
    assert "No blocked tact delivery items were detected." in render_tact_delivery_readiness_markdown(report)


def _ready(idea_id: str, priority: str) -> dict[str, object]:
    return {
        "idea_id": idea_id,
        "has_spec": True,
        "has_acceptance_criteria": True,
        "has_evidence_trace": True,
        "has_owner": True,
        "has_budget": True,
        "has_risk_notes": True,
        "priority": priority,
    }
