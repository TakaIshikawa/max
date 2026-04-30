"""Render validation experiments as an iCalendar feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


PRODID = "-//Max//Validation Experiments//EN"
UID_DOMAIN = "validation-experiments.max"


@dataclass(frozen=True)
class ValidationExperimentCalendarExport:
    """Rendered calendar text plus export counts."""

    text: str
    metadata: dict[str, int]


def render_validation_experiment_calendar(
    experiments: list[dict[str, Any]],
    *,
    ideas_by_id: dict[str, Any] | None = None,
    design_briefs_by_idea_id: dict[str, dict[str, Any]] | None = None,
    calendar_name: str = "Max Validation Experiments",
) -> ValidationExperimentCalendarExport:
    """Render dated validation experiments as RFC 5545-compatible VCALENDAR text."""

    ideas_by_id = ideas_by_id or {}
    design_briefs_by_idea_id = design_briefs_by_idea_id or {}

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_escape_text(PRODID)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape_text(calendar_name)}",
    ]

    omitted_without_due_date = 0
    omitted_invalid_due_date = 0
    exported_count = 0

    for experiment in sorted(experiments, key=_sort_key):
        raw_due_date = experiment.get("due_date")
        if not raw_due_date:
            omitted_without_due_date += 1
            continue
        due_date = _parse_due_date(str(raw_due_date))
        if due_date is None:
            omitted_invalid_due_date += 1
            continue

        lines.extend(_event_lines(experiment, due_date, ideas_by_id, design_briefs_by_idea_id))
        exported_count += 1

    lines.append("END:VCALENDAR")
    return ValidationExperimentCalendarExport(
        text="\r\n".join(_fold_line(line) for line in lines) + "\r\n",
        metadata={
            "total_count": len(experiments),
            "exported_count": exported_count,
            "omitted_without_due_date_count": omitted_without_due_date,
            "omitted_invalid_due_date_count": omitted_invalid_due_date,
        },
    )


def _event_lines(
    experiment: dict[str, Any],
    due_date: date,
    ideas_by_id: dict[str, Any],
    design_briefs_by_idea_id: dict[str, dict[str, Any]],
) -> list[str]:
    experiment_id = str(experiment.get("id") or "unknown")
    idea_id = str(experiment.get("idea_id") or "")
    idea = ideas_by_id.get(idea_id)
    design_brief = design_briefs_by_idea_id.get(idea_id)
    end_date = due_date + timedelta(days=1)

    return [
        "BEGIN:VEVENT",
        f"UID:{_escape_text(_event_uid(experiment_id, idea_id))}",
        "DTSTAMP:19700101T000000Z",
        f"DTSTART;VALUE=DATE:{due_date:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end_date:%Y%m%d}",
        f"SUMMARY:{_escape_text(_summary(experiment))}",
        f"DESCRIPTION:{_escape_text(_description(experiment, idea, design_brief))}",
        f"STATUS:{_calendar_status(experiment.get('status'))}",
        f"X-MAX-EXPERIMENT-ID:{_escape_text(experiment_id)}",
        f"X-MAX-IDEA-ID:{_escape_text(idea_id)}",
        f"X-MAX-VALIDATION-STATUS:{_escape_text(str(experiment.get('status') or 'unspecified'))}",
        "END:VEVENT",
    ]


def _event_uid(experiment_id: str, idea_id: str) -> str:
    key = f"{experiment_id}.{idea_id}" if idea_id else experiment_id
    return f"{key}@{UID_DOMAIN}"


def _summary(experiment: dict[str, Any]) -> str:
    hypothesis = str(experiment.get("hypothesis") or "").strip()
    return f"Validation experiment: {hypothesis or experiment.get('id') or 'untitled'}"


def _description(experiment: dict[str, Any], idea: Any, design_brief: dict[str, Any] | None) -> str:
    lines = [
        f"Hypothesis: {experiment.get('hypothesis') or ''}",
        f"Method: {experiment.get('method') or ''}",
        f"Success metric: {experiment.get('success_metric') or ''}",
        f"Status: {experiment.get('status') or 'unspecified'}",
    ]
    sample_size = experiment.get("target_sample_size")
    if sample_size is not None:
        lines.append(f"Target sample size: {sample_size}")
    idea_id = experiment.get("idea_id") or ""
    idea_title = getattr(idea, "title", "") if idea is not None else ""
    if idea_id:
        lines.append(f"Idea: {idea_title} ({idea_id})" if idea_title else f"Idea: {idea_id}")
    if design_brief:
        brief_label = design_brief.get("title") or design_brief.get("id")
        lines.append(f"Design brief: {brief_label} ({design_brief.get('id')})")
    result = str(experiment.get("result_summary") or "").strip()
    if result:
        lines.append(f"Result summary: {result}")
    evidence_urls = experiment.get("evidence_urls") or []
    if evidence_urls:
        lines.append("Evidence: " + ", ".join(str(url) for url in evidence_urls))
    return "\n".join(lines)


def _calendar_status(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"completed", "done", "validated"}:
        return "CONFIRMED"
    if normalized in {"cancelled", "canceled", "dropped"}:
        return "CANCELLED"
    return "TENTATIVE"


def _parse_due_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _sort_key(experiment: dict[str, Any]) -> tuple[str, str]:
    return (str(experiment.get("due_date") or "9999-99-99"), str(experiment.get("id") or ""))


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold_line(line: str) -> str:
    if len(line.encode("utf-8")) <= 75:
        return line
    chunks: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if current and len(candidate.encode("utf-8")) > 75:
            chunks.append(current)
            current = " " + char
        else:
            current = candidate
    chunks.append(current)
    return "\r\n".join(chunks)
