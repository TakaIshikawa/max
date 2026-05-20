"""Security training coverage report export."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.security_training_coverage.v1"
KIND = "max.security_training_coverage"

TrainingStatus = Literal["overdue", "incomplete", "expiring", "completed"]
GroupBy = Literal["team", "role", "campaign"]


class SecurityTrainingCoverageInput(TypedDict, total=False):
    learner: str
    person: str
    team: str
    role: str
    campaign: str
    training: str
    status: str
    completed: bool
    due_date: str
    expiration_date: str
    owner: str


def build_security_training_coverage_report(
    records: Iterable[SecurityTrainingCoverageInput | dict[str, Any]],
    *,
    title: str = "Security Training Coverage Report",
    group_by: GroupBy = "team",
    as_of: str = "2026-05-20",
    expiring_within_days: int = 30,
) -> dict[str, Any]:
    training = _normalize_training(records, as_of=as_of, expiring_within_days=expiring_within_days)
    groups = _groups(training, group_by)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Security Training Coverage Report",
        "group_by": group_by,
        "as_of": as_of,
        "summary": _coverage_summary(training),
        "groups": groups,
        "records": training,
    }


def render_security_training_coverage_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Security Training Coverage Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        f"As of: {report.get('as_of') or 'Unspecified'}",
        "",
        "## Summary",
        "",
        f"- Assigned records: {summary.get('assigned_count', 0)}",
        f"- Completed records: {summary.get('completed_count', 0)}",
        f"- Coverage: {summary.get('coverage_percent', 0)}%",
        f"- Overdue: {summary.get('overdue_count', 0)}",
        f"- Incomplete: {summary.get('incomplete_count', 0)}",
        f"- Expiring soon: {summary.get('expiring_count', 0)}",
        "",
        "## Coverage Register",
        "",
    ]
    groups = report.get("groups") or []
    if groups:
        for group in groups:
            coverage = group["coverage"]
            lines.extend(
                [
                    f"### {group['name']}",
                    "",
                    f"- Coverage: {coverage['completed_count']}/{coverage['assigned_count']} ({coverage['coverage_percent']}%)",
                    "",
                ]
            )
            for row in group["records"]:
                lines.extend(
                    [
                        f"#### {row['learner']} - {row['training']}",
                        f"- Team: {row['team']}",
                        f"- Role: {row['role']}",
                        f"- Campaign: {row['campaign']}",
                        f"- Status: {row['status']}",
                        f"- Due date: {row['due_date'] or 'Unscheduled'}",
                        f"- Expiration date: {row['expiration_date'] or 'Not supplied'}",
                        f"- Owner: {row['owner']}",
                        "",
                    ]
                )
    else:
        lines.append("- No security training records were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_security_training_coverage_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_training(
    records: Iterable[SecurityTrainingCoverageInput | dict[str, Any]],
    *,
    as_of: str,
    expiring_within_days: int,
) -> list[dict[str, Any]]:
    as_of_date = _parse_date(as_of)
    rows = []
    for raw in records:
        due_date = _text(raw.get("due_date"))
        expiration_date = _text(raw.get("expiration_date"))
        rows.append(
            {
                "learner": _text(raw.get("learner") or raw.get("person") or "Unassigned learner"),
                "team": _text(raw.get("team") or "Unassigned team"),
                "role": _text(raw.get("role") or "Unassigned role"),
                "campaign": _text(raw.get("campaign") or "Unassigned campaign"),
                "training": _text(raw.get("training") or "Security training"),
                "status": _status(raw, as_of_date=as_of_date, due_date=due_date, expiration_date=expiration_date, expiring_within_days=expiring_within_days),
                "due_date": due_date,
                "expiration_date": expiration_date,
                "owner": _text(raw.get("owner") or "Unassigned"),
            }
        )
    rows.sort(key=_training_sort_key)
    return rows


def _groups(records: list[dict[str, Any]], group_by: GroupBy) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row[group_by]].append(row)
    groups = [{"name": name, "coverage": _coverage_summary(items), "records": items} for name, items in grouped.items()]
    groups.sort(key=lambda group: (_group_worst_key(group["records"]), group["name"].lower()))
    return groups


def _coverage_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    assigned = len(records)
    completed = sum(1 for row in records if row["status"] == "completed")
    return {
        "assigned_count": assigned,
        "completed_count": completed,
        "coverage_percent": round((completed / assigned) * 100, 1) if assigned else 0.0,
        "overdue_count": sum(1 for row in records if row["status"] == "overdue"),
        "incomplete_count": sum(1 for row in records if row["status"] == "incomplete"),
        "expiring_count": sum(1 for row in records if row["status"] == "expiring"),
    }


_STATUS_ORDER = {"overdue": 0, "incomplete": 1, "expiring": 2, "completed": 3}


def _training_sort_key(row: dict[str, Any]) -> tuple[int, str, str, str, str]:
    return (
        _STATUS_ORDER[row["status"]],
        row["due_date"] or "9999-12-31",
        row["team"].lower(),
        row["role"].lower(),
        row["learner"].lower(),
    )


def _group_worst_key(records: list[dict[str, Any]]) -> tuple[int, str]:
    first = min(records, key=_training_sort_key)
    return (_STATUS_ORDER[first["status"]], first["due_date"] or "9999-12-31")


def _status(
    raw: SecurityTrainingCoverageInput | dict[str, Any],
    *,
    as_of_date: date,
    due_date: str,
    expiration_date: str,
    expiring_within_days: int,
) -> TrainingStatus:
    explicit = _text(raw.get("status")).lower()
    if explicit in {"overdue", "incomplete", "expiring", "completed"}:
        return explicit  # type: ignore[return-value]
    due = _parse_date(due_date)
    expires = _parse_date(expiration_date)
    completed = bool(raw.get("completed")) or explicit in {"complete", "done", "passed"}
    if not completed and due and due < as_of_date:
        return "overdue"
    if not completed:
        return "incomplete"
    if expires and 0 <= (expires - as_of_date).days <= expiring_within_days:
        return "expiring"
    return "completed"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.max


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
