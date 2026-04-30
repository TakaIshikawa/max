"""Tests for validation experiment iCalendar rendering."""

from __future__ import annotations

from max.analysis.validation_experiment_calendar import (
    render_validation_experiment_calendar,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def _experiment(
    experiment_id: str,
    *,
    due_date: str | None,
    hypothesis: str = "Teams will schedule follow-ups",
) -> dict:
    return {
        "id": experiment_id,
        "idea_id": "bu-calendar",
        "hypothesis": hypothesis,
        "method": "Problem interviews",
        "target_sample_size": 6,
        "success_metric": "4 of 6 report repeat pain",
        "status": "planned",
        "started_at": None,
        "due_date": due_date,
        "completed_at": None,
        "result_summary": "Needs commas, semicolons; and\nnewlines escaped.",
        "evidence_urls": ["https://example.com/a,b"],
        "confidence_delta": None,
        "created_at": "2026-04-30T00:00:00+00:00",
        "updated_at": "2026-04-30T00:00:00+00:00",
    }


def test_calendar_renders_one_event_per_dated_validation_experiment() -> None:
    export = render_validation_experiment_calendar(
        [
            _experiment("vexp-undated", due_date=None),
            _experiment("vexp-dated", due_date="2026-05-15"),
        ],
    )

    assert export.text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert export.text.endswith("END:VCALENDAR\r\n")
    assert export.text.count("BEGIN:VEVENT") == 1
    assert "DTSTART;VALUE=DATE:20260515\r\n" in export.text
    assert "DTEND;VALUE=DATE:20260516\r\n" in export.text
    assert export.metadata == {
        "total_count": 2,
        "exported_count": 1,
        "omitted_without_due_date_count": 1,
        "omitted_invalid_due_date_count": 0,
    }


def test_calendar_event_has_stable_uid_and_escaped_description() -> None:
    export = render_validation_experiment_calendar(
        [_experiment("vexp-escape", due_date="2026-05-15")]
    )
    unfolded = export.text.replace("\r\n ", "")

    assert "UID:vexp-escape.bu-calendar@validation-experiments.max\r\n" in export.text
    assert "STATUS:TENTATIVE\r\n" in export.text
    assert "Needs commas\\, semicolons\\; and\\nnewlines escaped." in unfolded
    assert "https://example.com/a\\,b" in unfolded


def test_calendar_description_includes_idea_and_design_brief_references() -> None:
    idea = BuildableUnit(
        id="bu-calendar",
        title="Onboarding Handoff Tracker",
        one_liner="Track revenue onboarding handoffs",
        category=BuildableCategory.APPLICATION,
        problem="manual handoffs stall",
        solution="owner prompts",
        value_proposition="reduce delayed onboarding",
    )

    export = render_validation_experiment_calendar(
        [_experiment("vexp-ref", due_date="2026-05-15")],
        ideas_by_id={"bu-calendar": idea},
        design_briefs_by_idea_id={
            "bu-calendar": {"id": "dbf-calendar", "title": "Revenue Onboarding Brief"}
        },
    )
    unfolded = export.text.replace("\r\n ", "")

    assert "Idea: Onboarding Handoff Tracker (bu-calendar)" in unfolded
    assert "Design brief: Revenue Onboarding Brief (dbf-calendar)" in unfolded
