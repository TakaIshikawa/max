"""LLM budget burn anomaly export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_budget_burn_anomaly_report.v1"
KIND = "max.llm_budget_burn_anomaly_report"
RISK_RANK = {"high": 0, "medium": 1, "low": 2}


def generate_llm_budget_burn_anomaly_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, float]] = defaultdict(lambda: {"observed_cost": 0.0, "expected_cost": 0.0, "observed_tokens": 0.0, "expected_tokens": 0.0})
    for raw in records:
        stage = _text(raw.get("pipeline_stage") or raw.get("stage") or raw.get("step")) or "unknown-stage"
        group = groups[stage]
        group["observed_cost"] += _num(raw.get("observed_cost") or raw.get("cost") or raw.get("actual_cost"))
        group["expected_cost"] += _num(raw.get("expected_cost") or raw.get("budget_cost") or raw.get("cost_budget"))
        group["observed_tokens"] += _num(raw.get("observed_tokens") or raw.get("tokens") or raw.get("actual_tokens") or raw.get("total_tokens"))
        group["expected_tokens"] += _num(raw.get("expected_tokens") or raw.get("budget_tokens") or raw.get("token_budget"))
    rows = []
    for stage, group in groups.items():
        variance_ratio = max(_ratio(group["observed_cost"] - group["expected_cost"], group["expected_cost"]), _ratio(group["observed_tokens"] - group["expected_tokens"], group["expected_tokens"]))
        risk = _risk(variance_ratio)
        rows.append({"pipeline_stage": stage, "observed_cost": round(group["observed_cost"], 4), "expected_cost": round(group["expected_cost"], 4), "observed_tokens": int(group["observed_tokens"]), "expected_tokens": int(group["expected_tokens"]), "variance_ratio": variance_ratio, "anomaly_risk": risk})
    rows.sort(key=lambda row: (RISK_RANK[row["anomaly_risk"]], -row["variance_ratio"], row["pipeline_stage"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"stage_count": len(rows), "observed_cost": round(sum(r["observed_cost"] for r in rows), 4), "observed_tokens": sum(r["observed_tokens"] for r in rows), "high_risk_count": sum(1 for r in rows if r["anomaly_risk"] == "high")}, "rows": rows}


def _risk(variance_ratio: float) -> str:
    if variance_ratio >= 1.0:
        return "high"
    if variance_ratio >= 0.25:
        return "medium"
    return "low"


def _ratio(delta: float, expected: float) -> float:
    return round(max(0.0, delta) / expected, 4) if expected > 0 else 0.0


def _num(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
