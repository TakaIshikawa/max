"""LLM budget variance export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.llm_budget_variance_report.v1"
KIND = "max.llm_budget_variance_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class LLMBudgetVarianceInput(TypedDict, total=False):
    run_id: str
    stage: str
    model: str
    budget_tokens: int | float | str
    actual_tokens: int | float | str
    budget_cost: int | float | str
    actual_cost: int | float | str
    request_count: int | float | str
    throttled: bool | str


def build_llm_budget_variance_report(
    records: Iterable[LLMBudgetVarianceInput | dict[str, Any]],
    *,
    title: str = "LLM Budget Variance Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    over = [row for row in rows if row["token_variance"] > 0 or row["cost_variance"] > 0]
    throttled = [row for row in rows if row["throttled"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "LLM Budget Variance Report",
        "summary": {
            "stage_count": len(rows),
            "over_budget_stage_count": len(over),
            "throttled_run_count": len({row["run_id"] for row in throttled}),
            "budget_tokens": sum(row["budget_tokens"] for row in rows),
            "actual_tokens": sum(row["actual_tokens"] for row in rows),
            "budget_cost": round(sum(row["budget_cost"] for row in rows), 4),
            "actual_cost": round(sum(row["actual_cost"] for row in rows), 4),
        },
        "stage_variance": rows,
        "over_budget_stages": sorted(over, key=lambda row: (-abs(row["cost_variance"]), -abs(row["token_variance"]), row["stage"].lower())),
        "throttled_runs": sorted(throttled, key=lambda row: (row["run_id"].lower(), row["stage"].lower())),
        "model_totals": _model_totals(rows),
        "containment_actions": [
            {
                "run_id": row["run_id"],
                "stage": row["stage"],
                "action": f"Review {row['stage']} budget controls for {row['model']}.",
            }
            for row in sorted(over, key=lambda row: (-abs(row["cost_variance"]), -abs(row["token_variance"]), row["stage"].lower()))
        ],
    }


def render_llm_budget_variance_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join(
        [
            f"# {report.get('title') or 'LLM Budget Variance Report'}",
            "",
            "## Summary",
            "",
            f"- Stages: {summary.get('stage_count', 0)}",
            f"- Over budget stages: {summary.get('over_budget_stage_count', 0)}",
            f"- Throttled runs: {summary.get('throttled_run_count', 0)}",
        ]
    ).rstrip() + "\n"


def render_llm_budget_variance_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[LLMBudgetVarianceInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        budget_tokens = _int(raw.get("budget_tokens"))
        actual_tokens = _int(raw.get("actual_tokens"))
        budget_cost = _float(raw.get("budget_cost"))
        actual_cost = _float(raw.get("actual_cost"))
        rows.append(
            {
                "run_id": _text(raw.get("run_id")) or "unknown-run",
                "stage": _text(raw.get("stage")) or "unknown-stage",
                "model": _text(raw.get("model")) or "unknown-model",
                "budget_tokens": budget_tokens,
                "actual_tokens": actual_tokens,
                "token_variance": actual_tokens - budget_tokens,
                "token_variance_rate": _rate(actual_tokens - budget_tokens, budget_tokens),
                "budget_cost": round(budget_cost, 4),
                "actual_cost": round(actual_cost, 4),
                "cost_variance": round(actual_cost - budget_cost, 4),
                "cost_variance_rate": _rate(actual_cost - budget_cost, budget_cost),
                "request_count": _int(raw.get("request_count")),
                "throttled": _bool(raw.get("throttled")),
            }
        )
    rows.sort(key=lambda row: (row["run_id"].lower(), row["stage"].lower(), row["model"].lower()))
    return rows


def _model_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    models = sorted({row["model"] for row in rows}, key=str.lower)
    return [
        {
            "model": model,
            "budget_tokens": sum(row["budget_tokens"] for row in rows if row["model"] == model),
            "actual_tokens": sum(row["actual_tokens"] for row in rows if row["model"] == model),
            "budget_cost": round(sum(row["budget_cost"] for row in rows if row["model"] == model), 4),
            "actual_cost": round(sum(row["actual_cost"] for row in rows if row["model"] == model), 4),
            "request_count": sum(row["request_count"] for row in rows if row["model"] == model),
        }
        for model in models
    ]


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "throttled"}


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
