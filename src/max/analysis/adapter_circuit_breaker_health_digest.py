"""Adapter circuit breaker health digest from persisted adapter run metrics."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.adapter_circuit_breaker_health_digest.v1"
KIND = "max.adapter_circuit_breaker_health_digest"

SUCCESS_STATUSES = {"ok", "success", "completed", "succeeded"}
HEALTH_BANDS = ("open", "at_risk", "healthy")
BAND_ORDER = {"open": 0, "at_risk": 1, "healthy": 2}
CSV_COLUMNS = (
    "adapter",
    "health_band",
    "run_count",
    "success_count",
    "failure_count",
    "failure_rate",
    "consecutive_failure_count",
    "latest_status",
    "latest_run_id",
    "latest_run_started_at",
    "last_error",
    "recommended_action",
)


def build_adapter_circuit_breaker_health_digest(
    store: "Store",
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a deterministic digest of adapter circuit breaker health."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    runs = store.get_pipeline_runs(limit=limit)
    adapters = [_adapter_row(adapter, rows) for adapter, rows in sorted(_adapter_runs(runs).items())]
    adapters.sort(key=_adapter_sort_key)
    health_bands = {
        band: [row["adapter"] for row in adapters if row["health_band"] == band]
        for band in HEALTH_BANDS
    }
    summary = {
        "run_count": len(runs),
        "adapter_count": len(adapters),
        "open_count": len(health_bands["open"]),
        "at_risk_count": len(health_bands["at_risk"]),
        "healthy_count": len(health_bands["healthy"]),
        "latest_run_started_at": runs[0]["started_at"] if runs else None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"limit": limit},
        "summary": summary,
        "adapters": adapters,
        "health_bands": health_bands,
        "next_actions": _next_actions(adapters, runs),
    }


def render_adapter_circuit_breaker_health_digest(
    report: Mapping[str, Any],
    *,
    fmt: str = "json",
) -> str:
    """Render adapter circuit breaker health as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported adapter circuit breaker health digest format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Adapter Circuit Breaker Health Digest",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Adapters ranked: {summary.get('adapter_count', 0)}",
        "",
        "## Summary",
        "",
        f"- Open: {summary.get('open_count', 0)}",
        f"- At risk: {summary.get('at_risk_count', 0)}",
        f"- Healthy: {summary.get('healthy_count', 0)}",
        "",
        "## Adapters",
        "",
    ]
    adapters = _list_of_maps(report.get("adapters"))
    if adapters:
        lines.append("| Adapter | Band | Runs | Failures | Streak | Latest Status | Last Error |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for row in adapters:
            lines.append(
                "| `{}` | {} | {} | {} | {} | `{}` | {} |".format(
                    row.get("adapter") or "",
                    row.get("health_band") or "",
                    row.get("run_count", 0),
                    row.get("failure_count", 0),
                    row.get("consecutive_failure_count", 0),
                    row.get("latest_status") or "",
                    row.get("last_error") or "",
                )
            )
    else:
        lines.append("No adapter metrics are available for this digest.")

    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in sorted(_list_of_maps(report.get("adapters")), key=_adapter_sort_key):
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    return output.getvalue()


def _adapter_runs(runs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        metrics = run.get("adapter_metrics")
        if not isinstance(metrics, Mapping):
            continue
        for adapter, raw_metrics in metrics.items():
            if not isinstance(raw_metrics, Mapping):
                continue
            status = str(raw_metrics.get("status") or "unknown").lower()
            grouped.setdefault(str(adapter), []).append(
                {
                    "run_id": run.get("id"),
                    "started_at": run.get("started_at"),
                    "status": status,
                    "success": status in SUCCESS_STATUSES,
                    "error": raw_metrics.get("error_message") or raw_metrics.get("error") or "",
                }
            )
    return grouped


def _adapter_row(adapter: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    run_count = len(rows)
    failure_count = sum(1 for row in rows if not row["success"])
    success_count = run_count - failure_count
    streak = 0
    for row in rows:
        if row["success"]:
            break
        streak += 1
    latest = rows[0]
    latest_failure = next((row for row in rows if not row["success"]), None)
    failure_rate = round(failure_count / run_count, 3) if run_count else 0.0
    band = _health_band(streak, failure_rate, failure_count)
    return {
        "adapter": adapter,
        "health_band": band,
        "run_count": run_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "failure_rate": failure_rate,
        "consecutive_failure_count": streak,
        "latest_status": latest["status"],
        "latest_run_id": latest["run_id"],
        "latest_run_started_at": latest["started_at"],
        "last_error": latest_failure["error"] if latest_failure and latest_failure["error"] else None,
        "recommended_action": _recommended_action(adapter, band, streak, latest_failure),
    }


def _health_band(streak: int, failure_rate: float, failure_count: int) -> str:
    if streak >= 2 or failure_rate >= 0.5:
        return "open"
    if streak == 1 or failure_count > 0:
        return "at_risk"
    return "healthy"


def _recommended_action(
    adapter: str,
    band: str,
    streak: int,
    latest_failure: Mapping[str, Any] | None,
) -> str:
    error = latest_failure.get("error") if latest_failure else ""
    suffix = f" Latest error: {error}." if error else ""
    if band == "open":
        return f"Throttle `{adapter}` and check credentials, quotas, or upstream availability before retrying.{suffix}"
    if band == "at_risk":
        return f"Tune retry and backoff settings for `{adapter}`; latest failure streak is {streak}.{suffix}"
    return f"Keep `{adapter}` enabled and monitor the next run."


def _next_actions(adapters: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[str]:
    if not adapters:
        if not runs:
            return ["Run the pipeline with adapter metrics enabled before reviewing circuit breaker health."]
        return ["Enable adapter_metrics persistence on pipeline runs before reviewing circuit breaker health."]

    actions: list[str] = []
    open_adapters = [row["adapter"] for row in adapters if row["health_band"] == "open"]
    at_risk = [row["adapter"] for row in adapters if row["health_band"] == "at_risk"]
    if open_adapters:
        actions.append(f"Throttle or pause open adapters first: {', '.join(open_adapters)}.")
        actions.append("Check credentials, quota exhaustion, and upstream outage signals for open adapters.")
    if at_risk:
        actions.append(f"Review retry tuning for at-risk adapters: {', '.join(at_risk)}.")
    if not actions:
        actions.append("Keep current adapter retry policy and revisit after the next pipeline run.")
    return actions


def _adapter_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        BAND_ORDER.get(str(row.get("health_band") or ""), len(BAND_ORDER)),
        -int(row.get("consecutive_failure_count") or 0),
        -float(row.get("failure_rate") or 0.0),
        str(row.get("adapter") or ""),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
