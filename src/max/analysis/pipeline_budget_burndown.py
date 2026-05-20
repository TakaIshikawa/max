"""Pipeline run budget burn-down analysis digest."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

from max.analysis.pipeline_run_export import _budget_summary, _domain_name, _profile_name, _run_status

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.pipeline_budget_burndown.v1"
KIND = "max.pipeline_budget_burndown"

_BAND_ORDER = {"over_limit": 0, "watch": 1, "ok": 2, "missing_usage": 3}
_CSV_COLUMNS = [
    "run_id",
    "started_at",
    "status",
    "profile",
    "domain",
    "estimated_cost_usd",
    "total_tokens",
    "budget_limit_usd",
    "budget_usage_ratio",
    "budget_band",
    "missing_usage",
]


def build_pipeline_budget_burndown(
    store: "Store",
    *,
    limit: int = 20,
    budget_limit_usd: float | None = None,
    profile_limits_usd: Mapping[str, float] | None = None,
    domain_limits_usd: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Build a deterministic budget burn-down digest for recent pipeline runs."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    default_limit = _optional_positive_limit(budget_limit_usd, "budget_limit_usd")
    profile_limits = _positive_limit_map(profile_limits_usd, "profile_limits_usd")
    domain_limits = _positive_limit_map(domain_limits_usd, "domain_limits_usd")

    raw_runs = store.get_pipeline_runs(limit=limit)
    rows = [_run_row(store, run, default_limit, profile_limits, domain_limits) for run in raw_runs]
    rows.sort(key=lambda row: (-row["estimated_cost_usd"], _reverse_text(row["started_at"]), row["id"]))

    bands = {
        band: [row["id"] for row in rows if row["budget_band"] == band]
        for band in ("over_limit", "watch", "ok", "missing_usage")
    }
    summary = _summary(rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "limit": limit,
            "budget_limit_usd": default_limit,
            "profile_limits_usd": dict(sorted(profile_limits.items())),
            "domain_limits_usd": dict(sorted(domain_limits.items())),
        },
        "summary": summary,
        "runs": rows,
        "budget_bands": bands,
        "next_actions": _next_actions(rows, summary),
    }


def render_pipeline_budget_burndown(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render a pipeline budget burn-down digest as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported pipeline budget burndown format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Pipeline Budget Burndown",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Runs analyzed: {summary.get('run_count', 0)}",
        f"Total estimated cost USD: {float(summary.get('total_estimated_cost_usd') or 0.0):.6f}",
        "",
        "## Summary",
        "",
        f"- Over limit: {summary.get('over_limit_count', 0)}",
        f"- Watch: {summary.get('watch_count', 0)}",
        f"- Missing usage: {summary.get('missing_usage_count', 0)}",
        f"- Cost trend: {summary.get('cost_trend') or 'unknown'}",
        "",
        "## Runs",
        "",
    ]

    runs = report.get("runs")
    if isinstance(runs, list) and runs:
        lines.append("| Run | Cost USD | Limit USD | Usage | Band | Profile | Domain | Started |")
        lines.append("| --- | ---: | ---: | ---: | --- | --- | --- | --- |")
        for row in runs:
            item = _mapping(row)
            ratio = item.get("budget_usage_ratio")
            usage = "" if ratio is None else f"{float(ratio):.3f}"
            limit = item.get("budget_limit_usd")
            limit_text = "" if limit is None else f"{float(limit):.6f}"
            lines.append(
                "| `{run}` | {cost:.6f} | {limit} | {usage} | {band} | `{profile}` | `{domain}` | {started} |".format(
                    run=item.get("id") or "",
                    cost=float(item.get("estimated_cost_usd") or 0.0),
                    limit=limit_text,
                    usage=usage,
                    band=item.get("budget_band") or "",
                    profile=item.get("profile") or "unknown",
                    domain=item.get("domain") or "mixed/unknown",
                    started=item.get("started_at") or "",
                )
            )
    else:
        lines.append("No pipeline runs are available for this report.")

    lines.extend(["", "## Profile Rollup", ""])
    _append_rollup_table(lines, summary.get("profiles"), "Profile")
    lines.extend(["", "## Domain Rollup", ""])
    _append_rollup_table(lines, summary.get("domains"), "Domain")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    if isinstance(actions, list) and actions:
        lines.extend(f"- {action}" for action in actions)
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    rows = report.get("runs")
    if not isinstance(rows, list):
        return output.getvalue()
    for row in sorted(
        rows,
        key=lambda item: (
            -_float(_mapping(item).get("estimated_cost_usd")),
            _reverse_text(_mapping(item).get("started_at")),
            str(_mapping(item).get("id") or ""),
        ),
    ):
        item = _mapping(row)
        writer.writerow(
            {
                "run_id": item.get("id") or "",
                "started_at": item.get("started_at") or "",
                "status": item.get("status") or "",
                "profile": item.get("profile") or "",
                "domain": item.get("domain") or "",
                "estimated_cost_usd": item.get("estimated_cost_usd", ""),
                "total_tokens": item.get("total_tokens", ""),
                "budget_limit_usd": item.get("budget_limit_usd", ""),
                "budget_usage_ratio": item.get("budget_usage_ratio", ""),
                "budget_band": item.get("budget_band") or "",
                "missing_usage": item.get("missing_usage", ""),
            }
        )
    return output.getvalue()


def _run_row(
    store: "Store",
    run: Mapping[str, Any],
    default_limit: float | None,
    profile_limits: Mapping[str, float],
    domain_limits: Mapping[str, float],
) -> dict[str, Any]:
    run_id = str(run["id"])
    domains = store.get_pipeline_run_domains(run_id)
    profile = _profile_name(run)
    domain = _domain_name(run, domains)
    budget = _budget_summary(run)
    cost = round(float(budget.get("estimated_cost_usd") or 0.0), 6)
    total_tokens = _nonnegative_int(budget.get("total_tokens"))
    limit = _run_limit(profile, domain, default_limit, profile_limits, domain_limits)
    ratio = round(cost / limit, 3) if limit else None
    missing_usage = total_tokens == 0 and cost == 0.0
    return {
        "id": run_id,
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "status": _run_status(run),
        "profile": profile,
        "domain": domain,
        "estimated_cost_usd": cost,
        "total_tokens": total_tokens,
        "input_tokens": _nonnegative_int(budget.get("input_tokens")),
        "output_tokens": _nonnegative_int(budget.get("output_tokens")),
        "budget_limit_usd": limit,
        "budget_usage_ratio": ratio,
        "budget_band": _budget_band(ratio, missing_usage),
        "missing_usage": missing_usage,
    }


def _run_limit(
    profile: str | None,
    domain: str | None,
    default_limit: float | None,
    profile_limits: Mapping[str, float],
    domain_limits: Mapping[str, float],
) -> float | None:
    if domain and domain in domain_limits:
        return domain_limits[domain]
    if profile and profile in profile_limits:
        return profile_limits[profile]
    return default_limit


def _budget_band(ratio: float | None, missing_usage: bool) -> str:
    if missing_usage:
        return "missing_usage"
    if ratio is None:
        return "ok"
    if ratio >= 1.0:
        return "over_limit"
    if ratio >= 0.8:
        return "watch"
    return "ok"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = round(sum(float(row["estimated_cost_usd"]) for row in rows), 6)
    return {
        "run_count": len(rows),
        "total_estimated_cost_usd": total,
        "average_estimated_cost_usd": round(total / len(rows), 6) if rows else 0.0,
        "highest_estimated_cost_usd": max((row["estimated_cost_usd"] for row in rows), default=0.0),
        "over_limit_count": sum(1 for row in rows if row["budget_band"] == "over_limit"),
        "watch_count": sum(1 for row in rows if row["budget_band"] == "watch"),
        "missing_usage_count": sum(1 for row in rows if row["missing_usage"]),
        "cost_trend": _cost_trend(rows),
        "profiles": _rollups(rows, "profile"),
        "domains": _rollups(rows, "domain"),
    }


def _rollups(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get(key) or "unknown")
        item = grouped.setdefault(
            name,
            {
                key: name,
                "run_count": 0,
                "estimated_cost_usd": 0.0,
                "over_limit_count": 0,
                "missing_usage_count": 0,
            },
        )
        item["run_count"] += 1
        item["estimated_cost_usd"] = round(item["estimated_cost_usd"] + row["estimated_cost_usd"], 6)
        item["over_limit_count"] += 1 if row["budget_band"] == "over_limit" else 0
        item["missing_usage_count"] += 1 if row["missing_usage"] else 0
    return sorted(grouped.values(), key=lambda item: (-item["estimated_cost_usd"], item[key]))


def _cost_trend(rows: list[dict[str, Any]]) -> str:
    chronological = sorted(rows, key=lambda row: (str(row.get("started_at") or ""), row["id"]))
    costs = [row["estimated_cost_usd"] for row in chronological if not row["missing_usage"]]
    if len(costs) < 2:
        return "insufficient_data"
    if all(later > earlier for earlier, later in zip(costs, costs[1:])):
        return "increasing"
    if all(later < earlier for earlier, later in zip(costs, costs[1:])):
        return "decreasing"
    return "mixed"


def _next_actions(rows: list[dict[str, Any]], summary: Mapping[str, Any]) -> list[str]:
    if not rows:
        return ["Run the pipeline with token usage tracking enabled before reviewing budget burn-down."]

    actions: list[str] = []
    missing = [row["id"] for row in rows if row["missing_usage"]]
    over_limit = [row["id"] for row in rows if row["budget_band"] == "over_limit"]
    watch = [row["id"] for row in rows if row["budget_band"] == "watch"]
    if missing:
        actions.append(f"Fix token usage capture for runs missing budget usage: {', '.join(missing)}.")
    if summary.get("cost_trend") == "increasing":
        actions.append("Review recent profile and domain changes because estimated run cost is increasing.")
    if over_limit:
        actions.append(f"Throttle or split over-limit runs before replaying: {', '.join(over_limit)}.")
    if watch:
        actions.append(f"Watch runs nearing configured budget limits: {', '.join(watch)}.")
    if not actions:
        actions.append("Keep current budget limits and compare again after the next scheduled run.")
    return actions


def _append_rollup_table(lines: list[str], rows: Any, label: str) -> None:
    if not isinstance(rows, list) or not rows:
        lines.append(f"No {label.lower()} cost rollups are available.")
        return
    key = label.lower()
    lines.append(f"| {label} | Runs | Cost USD | Over limit | Missing usage |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in rows:
        item = _mapping(row)
        lines.append(
            f"| `{item.get(key) or 'unknown'}` | {item.get('run_count', 0)} | "
            f"{float(item.get('estimated_cost_usd') or 0.0):.6f} | "
            f"{item.get('over_limit_count', 0)} | {item.get('missing_usage_count', 0)} |"
        )


def _optional_positive_limit(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return round(float(value), 6)


def _positive_limit_map(values: Mapping[str, float] | None, name: str) -> dict[str, float]:
    limits: dict[str, float] = {}
    for key, value in (values or {}).items():
        limits[str(key)] = _optional_positive_limit(value, f"{name}[{key}]") or 0.0
    return limits


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return max(0, int(value))
    return 0


def _reverse_text(value: Any) -> tuple[int, ...]:
    return tuple(-ord(char) for char in str(value or ""))
