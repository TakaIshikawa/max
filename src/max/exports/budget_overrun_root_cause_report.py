"""Budget overrun root-cause export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.budget_overrun_root_cause_report.v1"
KIND = "max.budget_overrun_root_cause_report"


class BudgetOverrunRootCauseInput(TypedDict, total=False):
    stage: str
    adapter: str
    model: str
    budget_tokens: int | float | str
    actual_tokens: int | float | str
    budget_cost: int | float | str
    actual_cost: int | float | str
    retry_count: int | float | str
    retry_tokens: int | float | str
    retry_cost: int | float | str


def build_budget_overrun_root_cause_report(records: Iterable[BudgetOverrunRootCauseInput | dict[str, Any]], *, title: str = "Budget Overrun Root Cause Report") -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records)]
    over = [row for row in rows if row["overrun_cost"] > 0 or row["overrun_tokens"] > 0]
    ranked = sorted(over, key=lambda row: (-row["overrun_cost"], -row["overrun_tokens"], row["stage"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Budget Overrun Root Cause Report",
        "summary": {"record_count": len(rows), "is_over_budget": bool(over), "budget_tokens": sum(row["budget_tokens"] for row in rows), "actual_tokens": sum(row["actual_tokens"] for row in rows), "budget_cost": round(sum(row["budget_cost"] for row in rows), 4), "actual_cost": round(sum(row["actual_cost"] for row in rows), 4), "overrun_cost": round(sum(row["overrun_cost"] for row in rows), 4), "retry_cost": round(sum(row["retry_cost"] for row in rows), 4)},
        "root_cause_ranking": ranked,
        "stage_totals": _totals(rows, "stage"),
        "adapter_totals": _totals(rows, "adapter"),
        "model_totals": _totals(rows, "model"),
        "retry_contribution": {"retry_count": sum(row["retry_count"] for row in rows), "retry_tokens": sum(row["retry_tokens"] for row in rows), "retry_cost": round(sum(row["retry_cost"] for row in rows), 4)},
        "recommended_guardrails": [_guardrail(row) for row in ranked] or ["No budget overrun detected; keep current guardrails."],
        "records": rows,
    }


def render_budget_overrun_root_cause_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [f"# {report.get('title') or 'Budget Overrun Root Cause Report'}", "", "## Budget Summary", "", f"- Over budget: {summary.get('is_over_budget', False)}", f"- Cost overrun: {summary.get('overrun_cost', 0)}", f"- Retry cost: {summary.get('retry_cost', 0)}", "", "## Root-Cause Ranking", ""]
    ranking = report.get("root_cause_ranking") or []
    if not ranking:
        lines.append("- No over-budget stages.")
    else:
        for row in ranking:
            lines.append(f"- {row['stage']} via {row['adapter']} using {row['model']}: cost +{row['overrun_cost']}, tokens +{row['overrun_tokens']}")
    lines.extend(["", "## Recommended Guardrails", ""])
    lines.extend([f"- {item}" for item in report.get("recommended_guardrails") or []])
    return "\n".join(lines).rstrip() + "\n"


def render_budget_overrun_root_cause_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    budget_tokens = _int(raw.get("budget_tokens"))
    actual_tokens = _int(raw.get("actual_tokens"))
    budget_cost = _float(raw.get("budget_cost"))
    actual_cost = _float(raw.get("actual_cost"))
    return {"stage": _text(raw.get("stage")) or f"stage-{index + 1}", "adapter": _text(raw.get("adapter")) or "unknown-adapter", "model": _text(raw.get("model")) or "unknown-model", "budget_tokens": budget_tokens, "actual_tokens": actual_tokens, "overrun_tokens": max(actual_tokens - budget_tokens, 0), "budget_cost": budget_cost, "actual_cost": actual_cost, "overrun_cost": round(max(actual_cost - budget_cost, 0), 4), "retry_count": _int(raw.get("retry_count")), "retry_tokens": _int(raw.get("retry_tokens")), "retry_cost": _float(raw.get("retry_cost"))}


def _totals(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    values = sorted({row[key] for row in rows}, key=str.lower)
    return [{key: value, "overrun_cost": round(sum(row["overrun_cost"] for row in rows if row[key] == value), 4), "overrun_tokens": sum(row["overrun_tokens"] for row in rows if row[key] == value), "retry_count": sum(row["retry_count"] for row in rows if row[key] == value)} for value in values]


def _guardrail(row: dict[str, Any]) -> str:
    return f"Add budget guardrail for {row['stage']} when {row['adapter']} retry loops exceed {max(row['retry_count'], 1)} attempts."


def _float(value: Any) -> float:
    try:
        return round(max(0.0, float(value)), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
