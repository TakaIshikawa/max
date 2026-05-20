"""Domain/profile pipeline run matrix analysis."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, Any

from max.analysis.pipeline_run_export import _domain_name, _profile_name, _run_status

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.domain_profile_run_matrix.v1"
KIND = "max.domain_profile_run_matrix"
CSV_COLUMNS = (
    "profile",
    "domain",
    "run_count",
    "success_rate",
    "average_ideas_generated",
    "average_score",
    "latest_run_at",
    "weak_reasons",
)


def build_domain_profile_run_matrix(
    store: "Store",
    *,
    limit: int = 50,
    min_success_rate: float = 0.8,
    min_average_ideas: float = 1.0,
    stale_after_days: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare recent pipeline runs across profile/domain combinations."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 0 <= min_success_rate <= 1:
        raise ValueError("min_success_rate must be between 0 and 1")
    if min_average_ideas < 0:
        raise ValueError("min_average_ideas must be non-negative")
    if stale_after_days < 1:
        raise ValueError("stale_after_days must be at least 1")

    current = _aware_utc(now or datetime.now(UTC))
    rows = _matrix_rows(store, store.get_pipeline_runs(limit=limit), current, min_success_rate, min_average_ideas, stale_after_days)
    weak = [row for row in rows if row["weak_reasons"]]
    summary = {
        "cell_count": len(rows),
        "weak_cell_count": len(weak),
        "run_count": sum(row["run_count"] for row in rows),
        "profile_count": len({row["profile"] for row in rows}),
        "domain_count": len({row["domain"] for row in rows}),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "limit": limit,
            "min_success_rate": min_success_rate,
            "min_average_ideas": min_average_ideas,
            "stale_after_days": stale_after_days,
        },
        "summary": summary,
        "matrix": rows,
        "weak_cells": weak,
        "next_actions": _next_actions(weak),
    }


def render_domain_profile_run_matrix(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render domain/profile run matrix as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported domain profile run matrix format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Domain Profile Run Matrix",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Cells: {summary.get('cell_count', 0)}",
        f"Weak cells: {summary.get('weak_cell_count', 0)}",
        "",
        "## Matrix",
        "",
        "| Profile | Domain | Runs | Success Rate | Avg Ideas | Avg Score | Latest Run | Weak Reasons |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in _list_of_maps(report.get("matrix")):
        lines.append(
            "| `{}` | `{}` | {} | {:.3f} | {:.2f} | {:.2f} | {} | {} |".format(
                row.get("profile") or "",
                row.get("domain") or "",
                row.get("run_count", 0),
                float(row.get("success_rate") or 0.0),
                float(row.get("average_ideas_generated") or 0.0),
                float(row.get("average_score") or 0.0),
                row.get("latest_run_at") or "",
                ", ".join(row.get("weak_reasons") or []),
            )
        )
    if not report.get("matrix"):
        lines.append("| none | none | 0 | 0.000 | 0.00 | 0.00 |  |  |")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _list_of_maps(report.get("matrix")):
        writer.writerow({**{key: row.get(key, "") for key in CSV_COLUMNS}, "weak_reasons": "; ".join(row.get("weak_reasons") or [])})
    return output.getvalue()


def _matrix_rows(
    store: "Store",
    runs: list[Mapping[str, Any]],
    now: datetime,
    min_success_rate: float,
    min_average_ideas: float,
    stale_after_days: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for run in runs:
        domains = store.get_pipeline_run_domains(str(run["id"]))
        profile = _profile_name(run) or "unknown"
        domain_rows = domains or [
            {
                "domain": _domain_name(run, domains) or "mixed/unknown",
                "ideas_generated": run.get("ideas_generated") or 0,
                "avg_score": run.get("avg_idea_score") or 0.0,
            }
        ]
        for domain_row in domain_rows:
            domain = str(domain_row.get("domain") or "mixed/unknown")
            grouped.setdefault((profile, domain), []).append(
                {
                    "run_id": run["id"],
                    "status": _run_status(run),
                    "ideas_generated": _number(domain_row.get("ideas_generated")),
                    "avg_score": _number(domain_row.get("avg_score")),
                    "started_at": run.get("started_at"),
                }
            )
    rows = []
    for (profile, domain), items in grouped.items():
        latest = max((str(item.get("started_at") or "") for item in items), default="")
        success_count = sum(1 for item in items if item["status"] == "completed")
        avg_ideas = sum(item["ideas_generated"] for item in items) / len(items)
        avg_score = sum(item["avg_score"] for item in items) / len(items)
        success_rate = success_count / len(items)
        latest_dt = _parse_timestamp(latest)
        stale = latest_dt is None or (now - latest_dt).days > stale_after_days
        reasons = []
        if success_rate < min_success_rate:
            reasons.append("low_success_rate")
        if avg_ideas < min_average_ideas:
            reasons.append("low_idea_output")
        if stale:
            reasons.append("stale_latest_run")
        rows.append(
            {
                "profile": profile,
                "domain": domain,
                "run_count": len(items),
                "success_rate": round(success_rate, 3),
                "average_ideas_generated": round(avg_ideas, 2),
                "average_score": round(avg_score, 2),
                "latest_run_at": latest,
                "weak_reasons": reasons,
            }
        )
    return sorted(rows, key=lambda row: (str(row["profile"]), str(row["domain"])))


def _next_actions(weak: list[dict[str, Any]]) -> list[str]:
    if not weak:
        return ["All analyzed domain/profile combinations meet run matrix thresholds."]
    return [
        "Inspect `{profile}` / `{domain}` for {reasons}.".format(
            profile=row["profile"],
            domain=row["domain"],
            reasons=", ".join(row["weak_reasons"]),
        )
        for row in weak[:5]
    ]


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
