"""Deterministic backlog report for validation experiments."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.validation_experiment_backlog_report.v1"
KIND = "max.validation_experiment_backlog_report"
DONE_STATUSES = {"completed", "cancelled"}
CSV_COLUMNS = (
    "id",
    "idea_id",
    "domain",
    "status",
    "status_band",
    "created_at",
    "due_date",
    "age_days",
    "target_metric",
    "rank_reason",
)


def build_validation_experiment_backlog_report(
    store: "Store",
    *,
    status: str | None = None,
    idea_id: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Rank validation experiments by backlog urgency."""
    current = today or datetime.now(UTC).date()
    experiments = store.query_validation_experiments(status=status, idea_id=idea_id)
    rows = [_experiment_row(item, current) for item in experiments]
    rows.sort(key=lambda row: (int(row["rank"]), str(row["created_at"] or ""), str(row["id"])))
    bands = {band: [row["id"] for row in rows if row["status_band"] == band] for band in ("blocked", "overdue", "pending", "active", "done")}
    summary = {
        "experiment_count": len(rows),
        "blocked_count": len(bands["blocked"]),
        "overdue_count": len(bands["overdue"]),
        "pending_count": len(bands["pending"]),
        "active_count": len(bands["active"]),
        "done_count": len(bands["done"]),
        "domain_count": len({row["domain"] for row in rows}),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"status": status, "idea_id": idea_id},
        "summary": summary,
        "status_bands": bands,
        "experiments": [{k: v for k, v in row.items() if k != "rank"} for row in rows],
        "next_actions": _next_actions(rows),
    }


def render_validation_experiment_backlog_report(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render validation experiment backlog as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported validation experiment backlog report format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Validation Experiment Backlog",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Experiments: {summary.get('experiment_count', 0)}",
        f"Blocked: {summary.get('blocked_count', 0)}",
        f"Overdue: {summary.get('overdue_count', 0)}",
        "",
        "## Experiments",
        "",
        "| Experiment | Idea | Domain | Status | Band | Age Days | Metric |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in _list_of_maps(report.get("experiments")):
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | {} | {} | {} |".format(
                row.get("id") or "",
                row.get("idea_id") or "",
                row.get("domain") or "",
                row.get("status") or "",
                row.get("status_band") or "",
                row.get("age_days", 0),
                row.get("target_metric") or "",
            )
        )
    if not report.get("experiments"):
        lines.append("| none | none | none | none | done | 0 | none |")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _list_of_maps(report.get("experiments")):
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _experiment_row(item: Mapping[str, Any], today: date) -> dict[str, Any]:
    status = str(item.get("status") or "planned")
    created = _parse_date(item.get("created_at"))
    due = _parse_date(item.get("due_date"))
    age = max((today - created).days, 0) if created else 0
    overdue = due is not None and due < today and status not in DONE_STATUSES
    band = _status_band(status, overdue)
    domain = str(item.get("domain") or "unspecified")
    return {
        "id": item.get("id"),
        "idea_id": item.get("idea_id"),
        "domain": domain,
        "status": status,
        "status_band": band,
        "created_at": item.get("created_at"),
        "due_date": item.get("due_date"),
        "age_days": age,
        "target_metric": item.get("success_metric") or "unspecified",
        "method": item.get("method") or "unspecified",
        "rank_reason": _rank_reason(band, age, item.get("success_metric"), domain),
        "rank": _rank(band, age, item.get("success_metric"), domain),
    }


def _status_band(status: str, overdue: bool) -> str:
    if status == "blocked":
        return "blocked"
    if overdue:
        return "overdue"
    if status in {"planned", "pending"}:
        return "pending"
    if status in {"running", "active"}:
        return "active"
    return "done"


def _rank(band: str, age: int, metric: Any, domain: str) -> int:
    band_rank = {"blocked": 0, "overdue": 1, "pending": 2, "active": 3, "done": 4}.get(band, 5)
    metric_penalty = 0 if str(metric or "").strip() else 1
    domain_penalty = 0 if domain != "unspecified" else 1
    return band_rank * 1_000_000 - min(age, 9999) * 100 + metric_penalty * 10 + domain_penalty


def _rank_reason(band: str, age: int, metric: Any, domain: str) -> str:
    parts = [band]
    if age:
        parts.append(f"{age}d old")
    if not str(metric or "").strip():
        parts.append("missing target metric")
    if domain == "unspecified":
        parts.append("missing idea domain")
    return ", ".join(parts)


def _next_actions(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Create validation experiments for approved ideas before backlog review."]
    counts = Counter(row["status_band"] for row in rows)
    actions = []
    if counts["blocked"]:
        actions.append(f"Unblock {counts['blocked']} validation experiment(s) before adding new work.")
    if counts["overdue"]:
        actions.append(f"Reschedule or complete {counts['overdue']} overdue validation experiment(s).")
    if counts["pending"]:
        actions.append(f"Start the oldest pending validation experiments with clear target metrics.")
    return actions or ["Continue monitoring active and completed validation experiments."]


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
