"""Model evaluation regression export report."""

from __future__ import annotations

import json
from typing import Any, Mapping

SCHEMA_VERSION = "max.model_eval_regression_report.v1"
KIND = "max.model_eval_regression_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_model_eval_regression_report(
    baseline_scores: Mapping[str, Any] | None,
    current_scores: Mapping[str, Any] | None,
    *,
    threshold: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
    title: str = "Model Eval Regression Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    """Compare current model eval scores against a baseline by metric."""

    baseline = baseline_scores or {}
    current = current_scores or {}
    regression_threshold = max(0.0, float(threshold))
    rows = [_metric_row(metric, baseline, current, regression_threshold) for metric in sorted(set(baseline) | set(current), key=str.casefold)]
    rows.sort(key=lambda row: (-row["regression_amount"], row["metric"].casefold()))
    gaps = [row for row in rows if row["status"] in {"missing_baseline", "missing_current"}]
    regressions = [row for row in rows if row["is_regression"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Model Eval Regression Report",
        "threshold": regression_threshold,
        "metadata": _jsonable(metadata or {}),
        "summary": {
            "metric_count": len(rows),
            "regression_count": len(regressions),
            "improvement_count": sum(1 for row in rows if row["status"] == "improved"),
            "gap_count": len(gaps),
            "largest_regression": max([row["regression_amount"] for row in regressions] or [0.0]),
        },
        "metrics": rows,
        "regressions": regressions,
        "gaps": gaps,
    }


def render_model_eval_regression_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _metric_row(metric: str, baseline: Mapping[str, Any], current: Mapping[str, Any], threshold: float) -> dict[str, Any]:
    has_baseline = metric in baseline
    has_current = metric in current
    baseline_score = _float(baseline.get(metric)) if has_baseline else None
    current_score = _float(current.get(metric)) if has_current else None
    if not has_baseline:
        delta = None
        regression_amount = 0.0
        status = "missing_baseline"
    elif not has_current:
        delta = None
        regression_amount = 0.0
        status = "missing_current"
    else:
        delta = round(current_score - baseline_score, 6)
        regression_amount = round(max(0.0, baseline_score - current_score), 6)
        if regression_amount > threshold:
            status = "regressed"
        elif delta > 0:
            status = "improved"
        else:
            status = "stable"
    return {
        "metric": _text(metric),
        "baseline_score": baseline_score,
        "current_score": current_score,
        "delta": delta,
        "absolute_delta": round(abs(delta), 6) if delta is not None else None,
        "regression_amount": regression_amount,
        "is_regression": status == "regressed",
        "status": status,
    }


def _float(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
