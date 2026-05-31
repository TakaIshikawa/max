"""Source adapter error budget breach export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_error_budget_breach_report.v1"
KIND = "max.source_adapter_error_budget_breach_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_source_adapter_error_budget_breach_report(records: Iterable[dict[str, Any]], *, include_all: bool = False, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: {"requests": 0.0, "errors": 0.0, "budget": 0.0})
    for item in records:
        key = (_text(item.get("adapter") or item.get("source")) or "adapter", _text(item.get("profile")) or "default", _text(item.get("window") or item.get("window_id")) or "current")
        groups[key]["requests"] += _num(item.get("request_count") or item.get("requests"))
        groups[key]["errors"] += _num(item.get("error_count") or item.get("errors"))
        groups[key]["budget"] = max(groups[key]["budget"], _rate(item.get("budget_error_rate") or item.get("error_budget_rate")))
    rows = []
    for (adapter, profile, window), values in groups.items():
        request_count = int(values["requests"])
        error_count = int(values["errors"])
        error_rate = error_count / request_count if request_count else 0.0
        budget = values["budget"] or 0.01
        breach = max(0.0, error_rate - budget)
        severity = "critical" if breach >= budget else ("warn" if breach > 0 else "ok")
        if include_all or breach > 0:
            rows.append({"adapter": adapter, "profile": profile, "window": window, "request_count": request_count, "error_count": error_count, "error_rate": round(error_rate, 4), "budget_error_rate": round(budget, 4), "breach_amount": round(breach, 4), "severity": severity, "recommended_action": "Throttle adapter and inspect failing responses." if severity == "critical" else ("Reduce adapter errors before next window." if severity == "warn" else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["breach_amount"], row["adapter"], row["profile"], row["window"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"adapter_count": len({row["adapter"] for row in rows}), "breach_count": sum(1 for row in rows if row["breach_amount"] > 0), "total_error_count": sum(row["error_count"] for row in rows), "critical_breach_count": sum(1 for row in rows if row["severity"] == "critical")}, "rows": rows}


def render_source_adapter_error_budget_breach_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_adapter_error_budget_breach_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Source Adapter Error Budget Breach Report", "", f"Breaches: {report.get('summary', {}).get('breach_count', 0)}", ""]
    if not report.get("rows"):
        lines.append("No error budget breaches found.")
    for row in report.get("rows") or []:
        lines.append(f"- {row['adapter']} / {row['profile']} / {row['window']}: {row['error_rate']} vs {row['budget_error_rate']} ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _rate(value: Any) -> float:
    number = _num(value)
    return number / 100 if number > 1 else number


def _num(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
