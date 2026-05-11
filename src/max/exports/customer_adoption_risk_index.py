"""Customer adoption risk index export for persisted buildable units."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_adoption_risk_index.v1"
KIND = "max.customer_adoption_risk_index"
_DIMENSIONS = (
    "target_user_clarity",
    "workflow_specificity",
    "buyer_strength",
    "validation_evidence",
    "onboarding_complexity",
    "pricing_friction",
    "support_readiness",
)
_LABELS = {
    "target_user_clarity": "Target user clarity",
    "workflow_specificity": "Workflow specificity",
    "buyer_strength": "Buyer strength",
    "validation_evidence": "Validation evidence",
    "onboarding_complexity": "Onboarding complexity",
    "pricing_friction": "Pricing friction",
    "support_readiness": "Support readiness",
}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_customer_adoption_risk_index_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_risk_row(unit) for unit in units]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["severity"]], -row["total_risk_score"], row["title"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_adoption_risk_index", "domain_filter": domain},
        "summary": _summary(rows),
        "risk_rows": rows,
    }


def render_customer_adoption_risk_index_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_customer_adoption_risk_index_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Customer Adoption Risk Index",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Ideas analyzed: {summary.get('idea_count', 0)}",
        f"- Average risk score: {summary.get('average_risk_score', 0.0):.1f}",
        f"- High risk: {summary.get('severity_counts', {}).get('high', 0)}",
        f"- Medium risk: {summary.get('severity_counts', {}).get('medium', 0)}",
        f"- Low risk: {summary.get('severity_counts', {}).get('low', 0)}",
        "",
        "## Risk Rows",
        "",
    ]
    if report.get("risk_rows"):
        lines.extend(["| Idea | Severity | Score | Drivers | Mitigation |", "|------|----------|-------|---------|------------|"])
        for row in report["risk_rows"]:
            lines.append(f"| {_md(row['title'])} | {row['severity']} | {row['total_risk_score']:.1f} | {_md(', '.join(row['risk_drivers']) or 'None')} | {_md(row['recommended_mitigation'])} |")
    else:
        lines.append("- No buildable units found.")
    lines.extend(["", "## Top Risk Drivers", ""])
    for driver in summary.get("top_risk_drivers") or []:
        lines.append(f"- {driver['driver']}: {driver['count']}")
    if not summary.get("top_risk_drivers"):
        lines.append("- No recurring risk drivers identified.")
    return "\n".join(lines).rstrip() + "\n"


def _risk_row(unit: Any) -> dict[str, Any]:
    scores = {dimension: _dimension_score(unit, dimension) for dimension in _DIMENSIONS}
    total = round(sum(scores.values()) / len(scores), 1)
    drivers = [_LABELS[key] for key, score in scores.items() if score >= 70.0]
    severity = "high" if total >= 70.0 else "medium" if total >= 40.0 else "low"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "severity": severity,
        "total_risk_score": total,
        "dimension_scores": scores,
        "risk_drivers": drivers,
        "recommended_mitigation": _mitigation(severity, drivers),
    }


def _dimension_score(unit: Any, dimension: str) -> float:
    metadata = getattr(unit, "metadata", {}) or {}
    direct = metadata.get(dimension) if isinstance(metadata, dict) else None
    if direct is not None:
        return _score_value(direct)
    if dimension == "target_user_clarity":
        return 10.0 if _text(getattr(unit, "specific_user", "")) else 85.0
    if dimension == "workflow_specificity":
        return 10.0 if _text(getattr(unit, "workflow_context", "")) else 80.0
    if dimension == "buyer_strength":
        return 15.0 if _text(getattr(unit, "buyer", "")) else 80.0
    if dimension == "validation_evidence":
        signals = _list(getattr(unit, "evidence_signals", [])) + _list(getattr(unit, "inspiring_insights", []))
        return 15.0 if signals or _text(getattr(unit, "validation_plan", "")) else 75.0
    if dimension == "onboarding_complexity":
        text = " ".join([_text(getattr(unit, "current_workaround", "")), _text(getattr(unit, "composability_notes", ""))]).lower()
        return 75.0 if any(term in text for term in ("manual", "migration", "training", "complex")) else 25.0
    if dimension == "pricing_friction":
        text = " ".join([_text(getattr(unit, "buyer", "")), _text(getattr(unit, "value_proposition", ""))]).lower()
        return 70.0 if any(term in text for term in ("procurement", "budget", "pricing", "enterprise")) else 25.0
    if dimension == "support_readiness":
        text = " ".join(_list(getattr(unit, "domain_risks", []))).lower()
        return 75.0 if "support" in text else 30.0
    return 0.0


def _score_value(value: Any) -> float:
    if isinstance(value, bool):
        return 20.0 if value else 80.0
    if isinstance(value, (int, float)):
        return max(0.0, min(100.0, float(value)))
    if isinstance(value, (list, tuple, set)):
        return 20.0 if value else 80.0
    normalized = str(value).strip().lower().replace(" ", "_")
    return {"low": 20.0, "clear": 15.0, "ready": 15.0, "medium": 55.0, "partial": 55.0, "high": 80.0, "unclear": 85.0, "blocked": 95.0}.get(normalized, 55.0)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {severity: sum(1 for row in rows if row["severity"] == severity) for severity in ("high", "medium", "low")}
    drivers = Counter(driver for row in rows for driver in row["risk_drivers"])
    return {
        "idea_count": len(rows),
        "average_risk_score": round(sum(row["total_risk_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "severity_counts": counts,
        "top_risk_drivers": [{"driver": driver, "count": count} for driver, count in sorted(drivers.items(), key=lambda item: (-item[1], item[0]))[:5]],
    }


def _mitigation(severity: str, drivers: list[str]) -> str:
    if not drivers:
        return "Keep customer adoption assumptions current as validation evidence changes."
    if severity == "high":
        return f"Resolve {drivers[0].lower()} before launch commitment and assign an adoption owner."
    return f"Review {drivers[0].lower()} during the next adoption readiness checkpoint."


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value or "").strip() else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
