"""Proof-of-concept ROI report export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.proof_of_concept_roi.v1"
KIND = "max.proof_of_concept_roi"

_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_proof_of_concept_roi_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_RISK_ORDER[row["risk_level"]], -row["roi_summary"]["net_value"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "proof_of_concept_roi", "domain_filter": domain},
        "roi_rows": rows,
        "summary": _summary(rows),
        "risk_flags": [flag for row in rows for flag in row["risk_flags"]],
        "recommended_next_actions": _recommendations(rows),
    }


def render_proof_of_concept_roi_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_proof_of_concept_roi_markdown(report: dict[str, Any]) -> str:
    lines = ["# Proof-of-Concept ROI Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## ROI", ""]
    if report.get("roi_rows"):
        lines.extend(["| Idea | Account | ROI | Net Value | Payback | Risk | Success Metrics | Next Action |", "|------|---------|-----|-----------|---------|------|-----------------|-------------|"])
        for row in report["roi_rows"]:
            summary = row["roi_summary"]
            lines.append(
                f"| {_md(row['title'])} | {_md(row['account'])} | {summary['roi_percent']}% | "
                f"{summary['net_value']} | {summary['payback_months']} | {row['risk_level']} | "
                f"{_md(', '.join(metric['metric'] for metric in row['success_metrics']) or 'None')} | "
                f"{_md(row['recommended_next_action'])} |"
            )
    else:
        lines.append("- No proof-of-concept ROI metadata available.")
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in report.get("recommended_next_actions", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    expected_value = _money(metadata.get("expected_revenue") or metadata.get("annual_contract_value") or metadata.get("benefit_value"))
    investment = _money(metadata.get("poc_investment") or metadata.get("investment") or metadata.get("cost"))
    labor_cost = _money(metadata.get("labor_cost") or metadata.get("services_cost"))
    tooling_cost = _money(metadata.get("tooling_cost") or metadata.get("infrastructure_cost"))
    total_cost = investment + labor_cost + tooling_cost
    metrics = _metrics(metadata.get("success_metrics"))
    blockers = _list(metadata.get("risk_flags") or metadata.get("blockers"))
    confidence = _score(metadata.get("confidence") or metadata.get("buyer_confidence"), default=60)
    net_value = expected_value - total_cost
    roi_percent = round((net_value / total_cost) * 100, 1) if total_cost else 0.0
    risk_flags = _risk_flags(total_cost, expected_value, metrics, blockers, confidence)
    risk_level = _risk_level(risk_flags)
    owner = _text(metadata.get("owner") or metadata.get("poc_owner") or "Unassigned")
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "account": _text(metadata.get("account") or metadata.get("customer") or metadata.get("segment") or "Unknown"),
        "roi_summary": {
            "expected_value": expected_value,
            "total_cost": total_cost,
            "net_value": net_value,
            "roi_percent": roi_percent,
            "payback_months": _payback_months(total_cost, expected_value),
            "confidence_score": confidence,
        },
        "cost_drivers": _cost_drivers(investment, labor_cost, tooling_cost, metadata),
        "success_metrics": metrics,
        "risk_flags": risk_flags,
        "risk_level": risk_level,
        "owner": owner,
        "recommended_next_action": _next_action(risk_level, owner, risk_flags),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "poc_count": len(rows),
        "total_expected_value": sum(row["roi_summary"]["expected_value"] for row in rows),
        "total_cost": sum(row["roi_summary"]["total_cost"] for row in rows),
        "total_net_value": sum(row["roi_summary"]["net_value"] for row in rows),
        "high_risk_count": sum(1 for row in rows if row["risk_level"] == "high"),
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture expected value, investment, success metrics, confidence, and risk flags for active proof-of-concepts."]
    recommendations = []
    if any(row["risk_level"] == "high" for row in rows):
        recommendations.append("Review high-risk proof-of-concepts before expanding investment.")
    if any(not row["success_metrics"] for row in rows):
        recommendations.append("Define measurable success metrics before executive ROI review.")
    if any(row["roi_summary"]["net_value"] > 0 and row["risk_level"] == "low" for row in rows):
        recommendations.append("Prepare low-risk positive ROI pilots for conversion planning.")
    return recommendations or ["Keep proof-of-concept ROI assumptions current through pilot close."]


def _cost_drivers(investment: int, labor_cost: int, tooling_cost: int, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    drivers = [
        {"driver": "poc investment", "amount": investment},
        {"driver": "labor cost", "amount": labor_cost},
        {"driver": "tooling cost", "amount": tooling_cost},
    ]
    for item in _list(metadata.get("cost_drivers")):
        drivers.append({"driver": item, "amount": 0})
    return [driver for driver in drivers if driver["amount"] or driver["driver"] not in {"labor cost", "tooling cost"}]


def _metrics(value: Any) -> list[dict[str, str]]:
    metrics = []
    for item in _list(value):
        if ":" in item:
            name, target = item.split(":", 1)
            metrics.append({"metric": _text(name), "target": _text(target)})
        else:
            metrics.append({"metric": item, "target": "tracked"})
    return metrics


def _risk_flags(total_cost: int, expected_value: int, metrics: list[dict[str, str]], blockers: list[str], confidence: int) -> list[dict[str, str]]:
    flags = [{"flag": blocker, "severity": "high"} for blocker in blockers]
    if total_cost and expected_value < total_cost:
        flags.append({"flag": "negative expected ROI", "severity": "high"})
    if total_cost == 0:
        flags.append({"flag": "missing investment estimate", "severity": "medium"})
    if not metrics:
        flags.append({"flag": "missing success metrics", "severity": "medium"})
    if confidence < 50:
        flags.append({"flag": "low buyer confidence", "severity": "medium"})
    return flags


def _risk_level(flags: list[dict[str, str]]) -> str:
    if any(flag["severity"] == "high" for flag in flags):
        return "high"
    if flags:
        return "medium"
    return "low"


def _next_action(risk_level: str, owner: str, flags: list[dict[str, str]]) -> str:
    if risk_level == "high":
        return f"{owner} to resolve {flags[0]['flag']} before ROI signoff."
    if risk_level == "medium":
        return f"{owner} to tighten ROI assumptions and success criteria."
    return "Advance to conversion plan with validated ROI assumptions."


def _payback_months(total_cost: int, expected_value: int) -> float | None:
    if total_cost <= 0 or expected_value <= 0:
        return None
    return round(total_cost / (expected_value / 12), 1)


def _money(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return max(0, round(float(str(value).replace("$", "").replace(",", "").strip())))
    except ValueError:
        return 0


def _score(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return round(max(0, min(100, float(str(value).rstrip("%")))))
    except ValueError:
        text = _text(value).lower()
        if any(word in text for word in ("high", "strong", "validated")):
            return 85
        if any(word in text for word in ("low", "weak", "uncertain")):
            return 35
        return default


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [_text(item) for item in value if _text(item)] if isinstance(value, (list, tuple, set)) else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
