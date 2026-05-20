"""Adapter allocation recommendations from run and utilization metrics."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.adapter_allocation_recommendations.v1"
KIND = "max.adapter_allocation_recommendations"

_SUCCESS_STATUSES = {"ok", "success", "completed"}
_ACTION_ORDER = {"pause": 0, "reduce": 1, "hold": 2, "increase": 3}
_CSV_COLUMNS = [
    "adapter_name",
    "action",
    "confidence",
    "priority",
    "run_count",
    "success_rate",
    "average_fetched_signals",
    "utilization_hit_rate",
    "latest_status",
    "latest_error",
    "recommendation",
]


def build_adapter_allocation_recommendations(
    store: "Store",
    *,
    limit: int = 20,
    min_runs: int = 1,
) -> dict[str, Any]:
    """Build deterministic adapter allocation recommendations."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if min_runs < 1:
        raise ValueError("min_runs must be at least 1")

    runs = store.get_pipeline_runs(limit=limit)
    quality_stats = store.get_adapter_quality_stats()
    rollups = _adapter_rollups(runs)
    adapters = sorted(rollups)
    rows = [
        _recommendation_row(adapter, rollups[adapter], quality_stats.get(adapter))
        for adapter in adapters
        if rollups[adapter]["run_count"] >= min_runs
    ]
    rows.sort(key=lambda row: (_ACTION_ORDER[row["action"]], -row["confidence"], row["adapter"]))

    bands = {
        action: [row["adapter"] for row in rows if row["action"] == action]
        for action in ("pause", "reduce", "hold", "increase")
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "limit": limit,
            "min_runs": min_runs,
        },
        "summary": {
            "run_count": len(runs),
            "adapter_count": len(rows),
            "excluded_below_min_runs_count": len(adapters) - len(rows),
            "pause_count": len(bands["pause"]),
            "reduce_count": len(bands["reduce"]),
            "hold_count": len(bands["hold"]),
            "increase_count": len(bands["increase"]),
            "latest_run_started_at": runs[0]["started_at"] if runs else None,
        },
        "recommendations": rows,
        "allocation_bands": bands,
        "next_actions": _next_actions(rows, runs=runs, quality_stats=quality_stats),
    }


def render_adapter_allocation_recommendations(
    report: Mapping[str, Any],
    *,
    fmt: str = "json",
) -> str:
    """Render adapter allocation recommendations as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported adapter allocation recommendations format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Adapter Allocation Recommendations",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Runs analyzed: {summary.get('run_count', 0)}",
        f"Adapters ranked: {summary.get('adapter_count', 0)}",
        "",
        "## Summary",
        "",
        f"- Pause: {summary.get('pause_count', 0)}",
        f"- Reduce: {summary.get('reduce_count', 0)}",
        f"- Hold: {summary.get('hold_count', 0)}",
        f"- Increase: {summary.get('increase_count', 0)}",
        "",
        "## Recommendations",
        "",
    ]

    rows = report.get("recommendations")
    if isinstance(rows, list) and rows:
        lines.append("| Adapter | Action | Confidence | Runs | Success | Avg fetched | Utilization | Latest |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        for row in rows:
            item = _mapping(row)
            latest = _mapping(item.get("latest_error_state"))
            latest_text = latest.get("error_message") or latest.get("status") or "unknown"
            lines.append(
                "| `{adapter}` | {action} | {confidence:.3f} | {runs} | {success:.3f} | "
                "{fetched:.2f} | {utilization:.3f} | {latest} |".format(
                    adapter=item.get("adapter") or "",
                    action=item.get("action") or "",
                    confidence=float(item.get("confidence") or 0.0),
                    runs=item.get("run_count", 0),
                    success=float(item.get("success_rate") or 0.0),
                    fetched=float(item.get("average_fetched_signals") or 0.0),
                    utilization=float(item.get("utilization_hit_rate") or 0.0),
                    latest=latest_text,
                )
            )
    else:
        lines.append("No adapter allocation metrics are available for this report.")

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
    rows = report.get("recommendations")
    if not isinstance(rows, list):
        return output.getvalue()
    for row in sorted(
        rows,
        key=lambda item: (
            _ACTION_ORDER.get(str(_mapping(item).get("action")), len(_ACTION_ORDER)),
            -_float(_mapping(item).get("confidence")),
            str(_mapping(item).get("adapter") or ""),
        ),
    ):
        item = _mapping(row)
        latest = _mapping(item.get("latest_error_state"))
        writer.writerow(
            {
                "adapter_name": item.get("adapter") or "",
                "action": item.get("action") or "",
                "confidence": item.get("confidence", ""),
                "priority": item.get("priority") or "",
                "run_count": item.get("run_count", ""),
                "success_rate": item.get("success_rate", ""),
                "average_fetched_signals": item.get("average_fetched_signals", ""),
                "utilization_hit_rate": item.get("utilization_hit_rate", ""),
                "latest_status": latest.get("status") or "",
                "latest_error": latest.get("error_message") or "",
                "recommendation": item.get("recommendation") or "",
            }
        )
    return output.getvalue()


def _adapter_rollups(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rollups: dict[str, dict[str, Any]] = {}
    for run in runs:
        metrics = run.get("adapter_metrics")
        if not isinstance(metrics, Mapping):
            continue
        for adapter, raw_metrics in metrics.items():
            if not isinstance(raw_metrics, Mapping):
                continue
            name = str(adapter)
            item = rollups.setdefault(
                name,
                {
                    "run_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "signal_count_total": 0,
                    "latest_status": "unknown",
                    "latest_error": "",
                },
            )
            status = str(raw_metrics.get("status") or "unknown")
            item["run_count"] += 1
            item["signal_count_total"] += _nonnegative_int(raw_metrics.get("signal_count"))
            if status in _SUCCESS_STATUSES:
                item["success_count"] += 1
            else:
                item["failure_count"] += 1
            if item["run_count"] == 1:
                item["latest_status"] = status
                item["latest_error"] = str(raw_metrics.get("error_message") or "")
    return rollups


def _recommendation_row(
    adapter: str,
    rollup: Mapping[str, Any],
    quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    run_count = _nonnegative_int(rollup.get("run_count"))
    success_count = _nonnegative_int(rollup.get("success_count"))
    failure_count = _nonnegative_int(rollup.get("failure_count"))
    success_rate = round(success_count / run_count, 3) if run_count else 0.0
    average_fetched = round(_nonnegative_int(rollup.get("signal_count_total")) / run_count, 3) if run_count else 0.0
    utilization = _utilization_hit_rate(quality)
    latest_status = str(rollup.get("latest_status") or "unknown")
    latest_error = str(rollup.get("latest_error") or "")
    action = _allocation_action(
        success_rate=success_rate,
        average_fetched=average_fetched,
        utilization_hit_rate=utilization,
        latest_status=latest_status,
        latest_error=latest_error,
    )
    confidence = _confidence(
        action=action,
        success_rate=success_rate,
        average_fetched=average_fetched,
        utilization_hit_rate=utilization,
        failure_count=failure_count,
    )
    return {
        "adapter": adapter,
        "action": action,
        "priority": f"p{_ACTION_ORDER[action]}",
        "confidence": confidence,
        "run_count": run_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "average_fetched_signals": average_fetched,
        "utilization_hit_rate": utilization,
        "latest_error_state": {
            "status": latest_status,
            "error_message": latest_error or None,
            "has_error": bool(latest_error) or latest_status not in _SUCCESS_STATUSES,
        },
        "recommendation": _recommendation_text(
            adapter,
            action=action,
            success_rate=success_rate,
            average_fetched=average_fetched,
            utilization_hit_rate=utilization,
            latest_error=latest_error,
        ),
    }


def _allocation_action(
    *,
    success_rate: float,
    average_fetched: float,
    utilization_hit_rate: float,
    latest_status: str,
    latest_error: str,
) -> str:
    latest_failed = latest_status not in _SUCCESS_STATUSES or bool(latest_error)
    if latest_failed and success_rate < 0.5:
        return "pause"
    if success_rate < 0.75 or average_fetched < 1.0 or utilization_hit_rate < 0.1:
        return "reduce"
    if success_rate >= 0.9 and average_fetched >= 3.0 and utilization_hit_rate >= 0.35 and not latest_failed:
        return "increase"
    return "hold"


def _confidence(
    *,
    action: str,
    success_rate: float,
    average_fetched: float,
    utilization_hit_rate: float,
    failure_count: int,
) -> float:
    yield_score = min(average_fetched / 5.0, 1.0)
    failure_score = min(failure_count / 3.0, 1.0)
    if action == "pause":
        value = 0.55 + failure_score * 0.25 + (1.0 - success_rate) * 0.20
    elif action == "reduce":
        value = 0.45 + (1.0 - success_rate) * 0.20 + (1.0 - yield_score) * 0.20 + (1.0 - utilization_hit_rate) * 0.15
    elif action == "increase":
        value = 0.45 + success_rate * 0.20 + yield_score * 0.15 + utilization_hit_rate * 0.20
    else:
        value = 0.50 + success_rate * 0.15 + yield_score * 0.10 + utilization_hit_rate * 0.10
    return round(min(value, 1.0), 3)


def _recommendation_text(
    adapter: str,
    *,
    action: str,
    success_rate: float,
    average_fetched: float,
    utilization_hit_rate: float,
    latest_error: str,
) -> str:
    if action == "pause":
        suffix = f" Latest error: {latest_error}." if latest_error else ""
        return f"Pause `{adapter}` allocation until failures are repaired.{suffix}"
    if action == "reduce":
        return (
            f"Reduce `{adapter}` allocation and retune queries; success={success_rate:.3f}, "
            f"average_fetched={average_fetched:.2f}, utilization={utilization_hit_rate:.3f}."
        )
    if action == "increase":
        return f"Increase `{adapter}` allocation while monitoring quality and quota headroom."
    return f"Hold `{adapter}` allocation and monitor for drift in the next run."


def _next_actions(
    rows: list[dict[str, Any]],
    *,
    runs: list[dict[str, Any]],
    quality_stats: Mapping[str, Any],
) -> list[str]:
    if not runs and not quality_stats:
        return ["Run the pipeline with adapter metrics enabled, then synthesize signals before changing allocations."]
    if not rows:
        return ["Lower min_runs or collect more pipeline runs before changing adapter allocation."]

    actions: list[str] = []
    pause = [row["adapter"] for row in rows if row["action"] == "pause"]
    reduce = [row["adapter"] for row in rows if row["action"] == "reduce"]
    increase = [row["adapter"] for row in rows if row["action"] == "increase"]
    if pause:
        actions.append(f"Pause allocation for failing adapters first: {', '.join(pause)}.")
    if reduce:
        actions.append(f"Reduce or retune low-confidence adapters: {', '.join(reduce)}.")
    if increase:
        actions.append(f"Shift spare allocation toward high-confidence adapters: {', '.join(increase)}.")
    if not actions:
        actions.append("Hold current allocation until new run or utilization data changes the ranking.")
    return actions


def _utilization_hit_rate(quality: Mapping[str, Any] | None) -> float:
    if quality is None:
        return 0.0
    return round(max(_rate(quality.get("insight_hit_rate")), _rate(quality.get("idea_hit_rate"))), 3)


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


def _rate(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return round(min(max(float(value), 0.0), 1.0), 3)
