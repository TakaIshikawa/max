"""Tests for validation experiment follow-up recommendations."""

from __future__ import annotations

import json
from datetime import date

from max.analysis.validation_followups import build_validation_followups
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _unit(unit_id: str = "bu-followups") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Validation Followups Idea",
        one_liner="Recommend validation next steps",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Experiment logs do not drive action",
        solution="Rank validation follow-up recommendations",
        value_proposition="Operators know the next validation move",
    )


def _actions(report: dict) -> list[str]:
    return [item["action"] for item in report["follow_up_actions"]]


def test_validation_followups_default_when_no_experiments(store: Store) -> None:
    store.insert_buildable_unit(_unit())

    report = build_validation_followups(store, "bu-followups", today=date(2026, 4, 30))

    assert report is not None
    assert report["latest_experiment"] is None
    assert report["status_counts"] == []
    assert report["evidence_url_count"] == 0
    assert report["confidence_delta_summary"] == {
        "count": 0,
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "total": 0.0,
        "average": None,
        "latest": None,
    }
    assert report["follow_up_actions"] == [
        {
            "rank": 1,
            "action": "schedule_followup",
            "reason": "No validation experiments are recorded; schedule the first validation step.",
            "experiment_id": None,
        }
    ]


def test_validation_followups_overdue_planned_experiment_schedules_followup(store: Store) -> None:
    store.insert_buildable_unit(_unit())
    experiment = store.create_validation_experiment(
        "bu-followups",
        hypothesis="Users will finish setup",
        method="prototype",
        success_metric="7 of 10 finish setup",
        status="planned",
        due_date="2026-04-01",
    )

    report = build_validation_followups(store, "bu-followups", today=date(2026, 4, 30))

    assert report is not None
    assert report["latest_experiment"]["id"] == experiment["id"]
    assert report["status_counts"] == [{"key": "planned", "count": 1}]
    assert report["follow_up_actions"][0]["action"] == "schedule_followup"
    assert report["follow_up_actions"][0]["experiment_id"] == experiment["id"]
    assert "overdue" in report["follow_up_actions"][0]["reason"]


def test_validation_followups_positive_completed_experiments_scale(
    store: Store,
) -> None:
    store.insert_buildable_unit(_unit())
    store.create_validation_experiment(
        "bu-followups",
        hypothesis="Teams will invite colleagues",
        method="concierge",
        success_metric="5 teams invite colleagues",
        status="completed",
        completed_at="2026-04-20T00:00:00+00:00",
        result_summary=json.dumps({"outcome": "validated"}),
        evidence_urls=["https://example.com/a"],
        confidence_delta=0.3,
    )
    latest_positive = store.create_validation_experiment(
        "bu-followups",
        hypothesis="Admins approve rollout",
        method="interview",
        success_metric="3 admins approve",
        status="completed",
        completed_at="2026-04-21T00:00:00+00:00",
        result_summary="4 admins approved rollout",
        evidence_urls=["https://example.com/b"],
        confidence_delta=0.2,
    )

    report = build_validation_followups(store, "bu-followups", today=date(2026, 4, 30))

    assert report is not None
    assert _actions(report) == ["scale"]
    assert report["evidence_url_count"] == 2
    assert report["confidence_delta_summary"]["average"] == 0.25
    assert report["follow_up_actions"][0]["experiment_id"] == latest_positive["id"]
    assert "evidence-backed upside" in report["follow_up_actions"][0]["reason"]


def test_validation_followups_negative_completed_experiments_pivot(
    store: Store,
) -> None:
    store.insert_buildable_unit(_unit())
    experiment = store.create_validation_experiment(
        "bu-followups",
        hypothesis="Buyers will pay for alerts",
        method="pricing interview",
        success_metric="4 paid commitments",
        status="completed",
        completed_at="2026-04-20T00:00:00+00:00",
        result_summary=json.dumps({"outcome": "invalidated"}),
        evidence_urls=["https://example.com/negative"],
        confidence_delta=-0.2,
    )

    report = build_validation_followups(store, "bu-followups", today=date(2026, 4, 30))

    assert report is not None
    assert _actions(report) == ["pivot"]
    assert report["confidence_delta_summary"]["negative_count"] == 1
    assert report["follow_up_actions"][0]["experiment_id"] == experiment["id"]
    assert "reduced confidence" in report["follow_up_actions"][0]["reason"]
    assert "Outcome: invalidated." in report["follow_up_actions"][0]["reason"]


def test_validation_followups_mixed_evidence_ranked_actions(
    store: Store,
) -> None:
    store.insert_buildable_unit(_unit())
    store.create_validation_experiment(
        "bu-followups",
        hypothesis="Users need a dashboard",
        method="prototype",
        success_metric="8 positive reactions",
        status="completed",
        completed_at="2026-04-20T00:00:00+00:00",
        evidence_urls=["https://example.com/positive-a", "https://example.com/positive-b"],
        confidence_delta=0.4,
    )
    store.create_validation_experiment(
        "bu-followups",
        hypothesis="Finance buyers approve budget",
        method="interview",
        success_metric="3 budget approvals",
        status="completed",
        completed_at="2026-04-22T00:00:00+00:00",
        result_summary="Budget owners declined the current package",
        evidence_urls=["https://example.com/negative"],
        confidence_delta=-0.1,
    )
    overdue = store.create_validation_experiment(
        "bu-followups",
        hypothesis="Operators complete onboarding",
        method="usability test",
        success_metric="6 completions",
        status="running",
        due_date="2026-04-10",
    )

    report = build_validation_followups(store, "bu-followups", today=date(2026, 4, 30))

    assert report is not None
    assert _actions(report) == ["schedule_followup", "pivot", "scale"]
    assert report["follow_up_actions"][0]["rank"] == 1
    assert report["follow_up_actions"][0]["experiment_id"] == overdue["id"]
    assert report["status_counts"] == [
        {"key": "completed", "count": 2},
        {"key": "running", "count": 1},
    ]


def test_validation_followups_returns_none_for_missing_idea(store: Store) -> None:
    assert build_validation_followups(store, "missing") is None
