"""LLM cost anomaly export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_cost_anomaly_report.v1"
KIND = "max.llm_cost_anomaly_report"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_llm_cost_anomaly_report(usage: Iterable[dict[str, Any]], *, anomaly_threshold: float = 0.2, critical_threshold: float = 0.5, include_healthy: bool = False) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {"expected_cost": 0.0, "actual_cost": 0.0, "models": set()})
    for item in usage:
        key = (_text(item.get("provider")) or "unknown", _text(item.get("stage")) or "unknown", _text(item.get("profile")) or "default", _text(item.get("model")) or "unknown")
        groups[key]["expected_cost"] += _float(item.get("expected_cost"))
        groups[key]["actual_cost"] += _float(item.get("actual_cost") or item.get("cost"))
    rows = []
    for (provider, stage, profile, model), totals in groups.items():
        expected = totals["expected_cost"]
        actual = totals["actual_cost"]
        variance = actual - expected
        pct = variance / expected if expected else (1.0 if actual else 0.0)
        severity = "critical" if pct >= critical_threshold else ("warn" if abs(pct) >= anomaly_threshold else "ok")
        if severity == "ok" and not include_healthy:
            continue
        rows.append({"provider": provider, "model": model, "stage": stage, "profile": profile, "expected_cost": round(expected, 4), "actual_cost": round(actual, 4), "variance": round(variance, 4), "variance_pct": round(pct, 4), "severity": severity, "remediation": "Investigate prompt/model routing and budget guardrails." if severity != "ok" else "No action required."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -abs(row["variance_pct"]), row["provider"], row["stage"], row["profile"], row["model"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"anomaly_count": sum(1 for row in rows if row["severity"] != "ok"), "row_count": len(rows)}, "rows": rows}


def render_llm_cost_anomaly_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_llm_cost_anomaly_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# LLM Cost Anomaly Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['provider']} {row['model']} / {row['stage']} / {row['profile']}: expected {row['expected_cost']}, actual {row['actual_cost']}, variance {row['variance']} ({row['severity']}). {row['remediation']}")
    return "\n".join(lines).rstrip() + "\n"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
