"""Pipeline run outcome reliability report from persisted run history."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

from max.analysis.pipeline_run_export import _domain_name, _profile_name, _run_status

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.pipeline_run_outcome_reliability.v1"
KIND = "max.pipeline_run_outcome_reliability"

SUCCESS_STATUSES = {"completed", "success", "succeeded", "ok"}
FAILURE_STATUSES = {"failed", "failure", "error"}
CANCELLED_STATUSES = {"cancelled", "canceled"}
STATUS_BANDS = ("success", "failure", "cancelled", "other")
CSV_COLUMNS = (
    "cohort_type",
    "cohort",
    "run_count",
    "success_count",
    "failure_count",
    "cancelled_count",
    "other_count",
    "success_rate",
    "failure_rate",
    "cancelled_rate",
    "reliability_band",
    "latest_failure_run_id",
    "latest_failure_at",
    "latest_error",
)


def build_pipeline_run_outcome_reliability(
    store: "Store",
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a deterministic reliability report for recent pipeline run outcomes."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    runs = [_run_row(store, run) for run in store.get_pipeline_runs(limit=limit)]
    cohorts = _cohorts(runs)
    status_bands = {
        band: [row["id"] for row in runs if row["status_band"] == band]
        for band in STATUS_BANDS
    }
    summary = _summary(runs, cohorts)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": summary,
        "cohorts": cohorts,
        "status_bands": status_bands,
        "next_actions": _next_actions(runs, cohorts),
    }


def render_pipeline_run_outcome_reliability(
    report: Mapping[str, Any],
    *,
    fmt: str = "json",
) -> str:
    """Render pipeline run outcome reliability as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported pipeline run outcome reliability format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Pipeline Run Outcome Reliability",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Runs analyzed: {summary.get('run_count', 0)}",
        f"Success rate: {float(summary.get('success_rate') or 0.0):.3f}",
        f"Failure rate: {float(summary.get('failure_rate') or 0.0):.3f}",
        "",
        "## Status Bands",
        "",
    ]
    for band in STATUS_BANDS:
        lines.append(f"- {band}: {len(_list(report.get('status_bands'), band))}")

    lines.extend(
        [
            "",
            "## Cohorts",
            "",
        ]
    )
    cohorts = _list_of_maps(report.get("cohorts"))
    if cohorts:
        lines.append("| Type | Cohort | Band | Runs | Success | Failure | Cancelled |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: |")
        for row in cohorts:
            lines.append(
                "| `{}` | `{}` | {} | {} | {:.3f} | {:.3f} | {:.3f} |".format(
                    row.get("cohort_type") or "",
                    row.get("cohort") or "",
                    row.get("reliability_band") or "",
                    row.get("run_count", 0),
                    float(row.get("success_rate") or 0.0),
                    float(row.get("failure_rate") or 0.0),
                    float(row.get("cancelled_rate") or 0.0),
                )
            )
    else:
        lines.append("No pipeline run cohorts are available for this report.")

    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in sorted(_list_of_maps(report.get("cohorts")), key=_cohort_sort_key):
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    return output.getvalue()


def _run_row(store: "Store", run: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(run.get("id") or "")
    domains = store.get_pipeline_run_domains(run_id)
    status = _run_status(run).lower()
    return {
        "id": run_id,
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "status": status,
        "status_band": _status_band(status),
        "profile": _profile_name(run) or "unknown",
        "domain": _domain_name(run, domains) or "mixed/unknown",
        "error_message": str(run.get("error_message") or ""),
    }


def _cohorts(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(("profile", run["profile"]), []).append(run)
        grouped.setdefault(("domain", run["domain"]), []).append(run)

    rows = [_cohort_row(cohort_type, cohort, items) for (cohort_type, cohort), items in grouped.items()]
    return sorted(rows, key=_cohort_sort_key)


def _cohort_row(cohort_type: str, cohort: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    run_count = len(runs)
    counts = {band: sum(1 for run in runs if run["status_band"] == band) for band in STATUS_BANDS}
    latest_failure = next((run for run in runs if run["status_band"] == "failure"), None)
    failure_rate = _rate(counts["failure"], run_count)
    cancelled_rate = _rate(counts["cancelled"], run_count)
    success_rate = _rate(counts["success"], run_count)
    return {
        "cohort_type": cohort_type,
        "cohort": cohort,
        "run_count": run_count,
        "success_count": counts["success"],
        "failure_count": counts["failure"],
        "cancelled_count": counts["cancelled"],
        "other_count": counts["other"],
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "cancelled_rate": cancelled_rate,
        "repeated_failure": counts["failure"] >= 2,
        "reliability_band": _reliability_band(failure_rate, cancelled_rate, success_rate),
        "latest_failure_run_id": latest_failure["id"] if latest_failure else None,
        "latest_failure_at": latest_failure["started_at"] if latest_failure else None,
        "latest_error": latest_failure["error_message"] if latest_failure and latest_failure["error_message"] else None,
    }


def _summary(runs: list[dict[str, Any]], cohorts: list[dict[str, Any]]) -> dict[str, Any]:
    run_count = len(runs)
    counts = {band: sum(1 for run in runs if run["status_band"] == band) for band in STATUS_BANDS}
    return {
        "run_count": run_count,
        "success_count": counts["success"],
        "failure_count": counts["failure"],
        "cancelled_count": counts["cancelled"],
        "other_count": counts["other"],
        "success_rate": _rate(counts["success"], run_count),
        "failure_rate": _rate(counts["failure"], run_count),
        "cancelled_rate": _rate(counts["cancelled"], run_count),
        "cohort_count": len(cohorts),
        "repeated_failure_cohort_count": sum(1 for row in cohorts if row["repeated_failure"]),
        "latest_run_started_at": runs[0]["started_at"] if runs else None,
    }


def _next_actions(runs: list[dict[str, Any]], cohorts: list[dict[str, Any]]) -> list[str]:
    if not runs:
        return [
            "Run the pipeline at least once before reviewing outcome reliability.",
            "Persist pipeline run status and error_message fields so failed cohorts can be triaged.",
        ]

    actions: list[str] = []
    failing = [row for row in cohorts if row["reliability_band"] == "failing"]
    degraded = [row for row in cohorts if row["reliability_band"] == "degraded"]
    repeated = [row for row in cohorts if row["repeated_failure"]]
    if repeated:
        names = ", ".join(f"{row['cohort_type']}:{row['cohort']}" for row in repeated[:3])
        actions.append(f"Investigate repeated pipeline failures for {names}.")
    if failing:
        names = ", ".join(f"{row['cohort_type']}:{row['cohort']}" for row in failing[:3])
        actions.append(f"Pause expansion for failing cohorts until run errors are resolved: {names}.")
    if degraded:
        names = ", ".join(f"{row['cohort_type']}:{row['cohort']}" for row in degraded[:3])
        actions.append(f"Watch degraded cohorts and compare their next run outcomes: {names}.")
    if not actions:
        actions.append("Keep current pipeline schedule and review reliability after the next run batch.")
    return actions


def _status_band(status: str) -> str:
    if status in SUCCESS_STATUSES:
        return "success"
    if status in FAILURE_STATUSES:
        return "failure"
    if status in CANCELLED_STATUSES:
        return "cancelled"
    return "other"


def _reliability_band(failure_rate: float, cancelled_rate: float, success_rate: float) -> str:
    if failure_rate >= 0.5:
        return "failing"
    if failure_rate > 0 or cancelled_rate >= 0.5:
        return "degraded"
    if success_rate >= 0.8:
        return "healthy"
    return "insufficient"


def _cohort_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -float(row.get("failure_rate") or 0.0),
        -int(row.get("failure_count") or 0),
        -float(row.get("cancelled_rate") or 0.0),
        float(row.get("success_rate") or 0.0),
        str(row.get("cohort_type") or ""),
        str(row.get("cohort") or ""),
    )


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any, key: str) -> list[Any]:
    mapping = _mapping(value)
    item = mapping.get(key)
    return item if isinstance(item, list) else []


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
