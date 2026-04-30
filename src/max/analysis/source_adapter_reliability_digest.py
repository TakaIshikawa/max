"""Source adapter reliability digest from persisted run and utilization metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.source_adapter.reliability_digest.v1"
KIND = "max.source_adapter.reliability_digest"

_SUCCESS_STATUSES = {"ok", "success", "completed"}
_BAND_ORDER = {
    "failing": 0,
    "low_yield": 1,
    "watch": 2,
    "healthy": 3,
}


def build_source_adapter_reliability_digest(
    store: Store,
    limit: int = 20,
    min_runs: int = 1,
) -> dict[str, Any]:
    """Build a deterministic reliability digest for source adapters."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if min_runs < 1:
        raise ValueError("min_runs must be at least 1")

    runs = store.get_pipeline_runs(limit=limit)
    quality_stats = store.get_adapter_quality_stats()
    adapter_rollups = _adapter_rollups(runs)
    adapters = sorted(adapter_rollups)

    rows = [
        _adapter_report(adapter, adapter_rollups[adapter], quality_stats.get(adapter))
        for adapter in adapters
        if adapter_rollups[adapter]["run_count"] >= min_runs
    ]
    rows.sort(key=lambda row: (_BAND_ORDER[row["reliability_band"]], row["reliability_score"], row["adapter"]))

    bands = {
        band: [row["adapter"] for row in rows if row["reliability_band"] == band]
        for band in ("failing", "low_yield", "watch", "healthy")
    }
    next_actions = _report_next_actions(rows, runs=runs, quality_stats=quality_stats)

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
            "healthy_count": len(bands["healthy"]),
            "watch_count": len(bands["watch"]),
            "low_yield_count": len(bands["low_yield"]),
            "failing_count": len(bands["failing"]),
            "latest_run_started_at": runs[0]["started_at"] if runs else None,
        },
        "reliability_bands": bands,
        "adapters": rows,
        "next_actions": next_actions,
    }


def render_source_adapter_reliability_digest(
    report: dict[str, Any],
    fmt: str = "json",
) -> str:
    """Render a source adapter reliability digest as deterministic JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported source adapter reliability digest format: {fmt}")

    summary = report["summary"]
    lines = [
        "# Source Adapter Reliability Digest",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Runs analyzed: {summary['run_count']}",
        f"Adapters ranked: {summary['adapter_count']}",
        "",
        "## Summary",
        "",
        f"- Failing: {summary['failing_count']}",
        f"- Low yield: {summary['low_yield_count']}",
        f"- Watch: {summary['watch_count']}",
        f"- Healthy: {summary['healthy_count']}",
        "",
        "## Adapter Rankings",
        "",
    ]

    if report["adapters"]:
        lines.append("| Adapter | Band | Score | Runs | Success | Failure | Avg fetched | Utilization |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in report["adapters"]:
            utilization = row["utilization"]
            lines.append(
                f"| `{row['adapter']}` | {row['reliability_band']} | "
                f"{row['reliability_score']:.3f} | {row['run_count']} | "
                f"{row['success_count']} | {row['failure_count']} | "
                f"{row['average_fetched_signals']:.2f} | "
                f"{utilization['combined_hit_rate']:.3f} |"
            )
    else:
        lines.append("No adapter run metrics are available for this report.")

    lines.extend(["", "## Follow-Up Actions", ""])
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines).rstrip() + "\n"


def _adapter_rollups(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rollups: dict[str, dict[str, Any]] = {}
    for run in runs:
        adapter_metrics = run.get("adapter_metrics") or {}
        if not isinstance(adapter_metrics, Mapping):
            continue
        for adapter, raw_metrics in adapter_metrics.items():
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
                    "duration_ms_total": 0,
                    "duration_ms_count": 0,
                    "last_error": "",
                    "latest_status": "unknown",
                },
            )
            status = str(raw_metrics.get("status") or "unknown")
            signal_count = _nonnegative_int(raw_metrics.get("signal_count"))
            duration_ms = raw_metrics.get("duration_ms")

            item["run_count"] += 1
            item["signal_count_total"] += signal_count
            if isinstance(duration_ms, int | float) and duration_ms >= 0:
                item["duration_ms_total"] += float(duration_ms)
                item["duration_ms_count"] += 1
            if status in _SUCCESS_STATUSES:
                item["success_count"] += 1
            else:
                item["failure_count"] += 1
                error = raw_metrics.get("error_message")
                if not item["last_error"] and error:
                    item["last_error"] = str(error)
            if item["run_count"] == 1:
                item["latest_status"] = status
    return rollups


def _adapter_report(
    adapter: str,
    rollup: dict[str, Any],
    quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    run_count = int(rollup["run_count"])
    success_count = int(rollup["success_count"])
    failure_count = int(rollup["failure_count"])
    average_fetched = round(float(rollup["signal_count_total"]) / run_count, 3)
    success_rate = round(success_count / run_count, 3)
    average_duration_ms = None
    if rollup["duration_ms_count"]:
        average_duration_ms = round(rollup["duration_ms_total"] / rollup["duration_ms_count"], 1)

    utilization = _utilization_stats(quality)
    score = _reliability_score(
        success_rate=success_rate,
        average_fetched=average_fetched,
        utilization_rate=utilization["combined_hit_rate"],
    )
    band = _reliability_band(
        success_rate=success_rate,
        failure_count=failure_count,
        average_fetched=average_fetched,
        utilization_rate=utilization["combined_hit_rate"],
    )

    return {
        "adapter": adapter,
        "reliability_band": band,
        "reliability_score": score,
        "run_count": run_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "latest_status": rollup["latest_status"],
        "last_error": rollup["last_error"] or None,
        "average_fetched_signals": average_fetched,
        "average_duration_ms": average_duration_ms,
        "utilization": utilization,
        "recommendations": _adapter_recommendations(
            adapter,
            band=band,
            failure_count=failure_count,
            success_rate=success_rate,
            average_fetched=average_fetched,
            utilization=utilization,
            last_error=rollup["last_error"],
        ),
    }


def _utilization_stats(quality: Mapping[str, Any] | None) -> dict[str, Any]:
    total_signals = _nonnegative_int((quality or {}).get("total_signals"))
    insight_hit_rate = _rate((quality or {}).get("insight_hit_rate"))
    idea_hit_rate = _rate((quality or {}).get("idea_hit_rate"))
    combined_hit_rate = round(max(insight_hit_rate, idea_hit_rate), 3)
    return {
        "available": quality is not None,
        "total_signals": total_signals,
        "insight_hit_rate": insight_hit_rate,
        "idea_hit_rate": idea_hit_rate,
        "combined_hit_rate": combined_hit_rate,
    }


def _reliability_score(
    *,
    success_rate: float,
    average_fetched: float,
    utilization_rate: float,
) -> float:
    yield_score = min(average_fetched / 5.0, 1.0)
    return round((success_rate * 0.55) + (yield_score * 0.25) + (utilization_rate * 0.20), 3)


def _reliability_band(
    *,
    success_rate: float,
    failure_count: int,
    average_fetched: float,
    utilization_rate: float,
) -> str:
    if failure_count > 0 and success_rate < 0.5:
        return "failing"
    if average_fetched < 1.0 or utilization_rate < 0.1:
        return "low_yield"
    if success_rate < 0.8 or average_fetched < 3.0 or utilization_rate < 0.25:
        return "watch"
    return "healthy"


def _adapter_recommendations(
    adapter: str,
    *,
    band: str,
    failure_count: int,
    success_rate: float,
    average_fetched: float,
    utilization: dict[str, Any],
    last_error: str,
) -> list[str]:
    recommendations: list[str] = []
    if band == "failing":
        error_hint = f" Last error: {last_error}." if last_error else ""
        recommendations.append(
            f"Repair `{adapter}` before increasing allocation; latest runs are failing.{error_hint}"
        )
    if failure_count and band != "failing":
        recommendations.append(
            f"Inspect intermittent `{adapter}` failures and add retry or quota handling."
        )
    if average_fetched < 1.0:
        recommendations.append(
            f"Lower `{adapter}` allocation or update query parameters because recent runs fetch few signals."
        )
    if utilization["available"] and utilization["total_signals"] > 0 and utilization["combined_hit_rate"] < 0.1:
        recommendations.append(
            f"Review `{adapter}` signal quality; persisted signals are rarely used by insights or ideas."
        )
    if not utilization["available"]:
        recommendations.append(
            f"Collect and synthesize `{adapter}` signals so utilization rates can be measured."
        )
    if not recommendations and success_rate >= 0.8:
        recommendations.append(f"Keep `{adapter}` enabled at current allocation and monitor drift.")
    return recommendations


def _report_next_actions(
    rows: list[dict[str, Any]],
    *,
    runs: list[dict[str, Any]],
    quality_stats: Mapping[str, Any],
) -> list[str]:
    if not runs and not quality_stats:
        return [
            "Run the pipeline with adapter metrics enabled, then synthesize signals to populate utilization stats."
        ]
    if not rows:
        return [
            "Lower min_runs or collect more pipeline runs before ranking adapter reliability."
        ]

    actions: list[str] = []
    failing = [row["adapter"] for row in rows if row["reliability_band"] == "failing"]
    low_yield = [row["adapter"] for row in rows if row["reliability_band"] == "low_yield"]
    watch = [row["adapter"] for row in rows if row["reliability_band"] == "watch"]
    if failing:
        actions.append(f"Repair failing adapters first: {', '.join(failing)}.")
    if low_yield:
        actions.append(f"Reduce allocation or retune low-yield adapters: {', '.join(low_yield)}.")
    if watch:
        actions.append(f"Monitor watch-list adapters for retry, quota, or relevance drift: {', '.join(watch)}.")
    if not actions:
        actions.append("Keep current adapter allocation and revisit after the next pipeline run.")
    return actions


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return max(0, int(value))
    return 0


def _rate(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if not isinstance(value, int | float):
        return 0.0
    return round(min(max(float(value), 0.0), 1.0), 3)
