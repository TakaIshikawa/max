"""SLA breach risk export for customer commitments."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.sla_breach_risk.v1"
KIND = "max.sla_breach_risk"
_FIELDS = ["idea_id", "title", "customer_tier", "sla_uptime_target", "observed_uptime", "uptime_breach_risk", "response_time_target_ms", "p95_response_time_ms", "latency_breach_risk", "error_budget_remaining", "error_budget_breach_risk", "contract_value", "financial_exposure", "escalation_priority", "confidence"]


def build_sla_breach_risk_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_row(unit) for unit in units]
    rows.sort(key=lambda row: (_priority_rank(row["escalation_priority"]), -row["financial_exposure"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "sla_breach_risk", "domain_filter": domain},
        "sla_row_count": len(rows),
        "sla_rows": rows,
        "summary": _summary(rows),
    }


def render_sla_breach_risk_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SLA Breach Risk",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        "| Priority | Count |",
        "|----------|-------|",
    ]
    for priority, count in report.get("summary", {}).get("priority_counts", {}).items():
        lines.append(f"| {priority} | {count} |")
    lines.extend(["", "## High Priority Breaches", ""])
    high = [row for row in report.get("sla_rows", []) if row["escalation_priority"] == "high"]
    if high:
        lines.extend(["| Unit | Tier | Risks | Exposure |", "|------|------|-------|----------|"])
        for row in high:
            lines.append(f"| {row['title']} | {row['customer_tier']} | {', '.join(row['breach_indicators'])} | ${row['financial_exposure']:,.0f} |")
    else:
        lines.append("- No high-priority SLA risks detected.")
    lines.extend(["", "## Tier Aggregation", "", "| Tier | Units | Exposure | High | Medium | Low |", "|------|-------|----------|------|--------|-----|"])
    for row in report.get("summary", {}).get("by_customer_tier", []):
        lines.append(f"| {row['customer_tier']} | {row['unit_count']} | ${row['financial_exposure']:,.0f} | {row['priority_counts']['high']} | {row['priority_counts']['medium']} | {row['priority_counts']['low']} |")
    return "\n".join(lines).rstrip() + "\n"


def render_sla_breach_risk_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_sla_breach_risk_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("sla_rows", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    target = _float(metadata.get("sla_uptime_target"), 99.9)
    observed = _float(metadata.get("observed_uptime"), 99.9)
    latency_target = _float(metadata.get("response_time_target_ms"), 500.0)
    p95 = _float(metadata.get("p95_response_time_ms"), latency_target)
    budget = _float(metadata.get("error_budget_remaining"), 1.0)
    tier = str(metadata.get("customer_tier") or "standard").lower()
    contract_value = max(_float(metadata.get("contract_value"), 0.0), 0.0)
    uptime_risk = observed < target
    latency_risk = p95 > latency_target
    budget_risk = budget <= 0.1
    indicators = [name for name, flag in [("uptime", uptime_risk), ("latency", latency_risk), ("error_budget", budget_risk)] if flag]
    confidence = "high" if any(key in metadata for key in ("sla_uptime_target", "observed_uptime", "response_time_target_ms", "p95_response_time_ms", "error_budget_remaining")) else "low"
    priority = _priority(len(indicators), tier, contract_value)
    exposure_multiplier = 0.6 if priority == "high" else 0.3 if priority == "medium" else 0.1
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "customer_tier": tier,
        "sla_uptime_target": target,
        "observed_uptime": observed,
        "uptime_breach_risk": uptime_risk,
        "response_time_target_ms": latency_target,
        "p95_response_time_ms": p95,
        "latency_breach_risk": latency_risk,
        "error_budget_remaining": budget,
        "error_budget_breach_risk": budget_risk,
        "breach_indicators": indicators,
        "contract_value": round(contract_value, 2),
        "financial_exposure": round(contract_value * exposure_multiplier, 2),
        "escalation_priority": priority,
        "confidence": confidence,
    }


def _priority(breach_count: int, tier: str, contract_value: float) -> str:
    score = breach_count * 2
    if tier in {"enterprise", "strategic"}:
        score += 2
    elif tier == "premium":
        score += 1
    if contract_value >= 100_000:
        score += 2
    elif contract_value >= 25_000:
        score += 1
    if score >= 5:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["customer_tier"]].append(row)
    return {
        "priority_counts": {priority: sum(1 for row in rows if row["escalation_priority"] == priority) for priority in ["high", "medium", "low"]},
        "financial_exposure": round(sum(row["financial_exposure"] for row in rows), 2),
        "by_customer_tier": [
            {"customer_tier": tier, "unit_count": len(items), "financial_exposure": round(sum(row["financial_exposure"] for row in items), 2), "priority_counts": {priority: sum(1 for row in items if row["escalation_priority"] == priority) for priority in ["high", "medium", "low"]}}
            for tier, items in sorted(groups.items())
        ],
    }


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _priority_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)
