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

DIMENSIONS = (
    "target_user_clarity",
    "workflow_specificity",
    "buyer_strength",
    "validation_evidence",
    "onboarding_complexity",
    "pricing_friction",
    "support_readiness",
)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_customer_adoption_risk_index_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_risk_row(unit) for unit in units]
    rows.sort(key=lambda row: (SEVERITY_ORDER[row["severity"]], -row["total_risk_score"], row["title"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_adoption_risk_index", "domain_filter": domain},
        "summary": _summary(rows),
        "risk_rows": rows,
    }


def render_customer_adoption_risk_index_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Customer Adoption Risk Index",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Generated: {report.get('generated_at')}",
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
        lines.append("- No buildable units found. Add adoption metadata before launch planning.")
    lines.extend(["", "## Top Risk Drivers", ""])
    for driver in summary.get("top_risk_drivers") or []:
        lines.append(f"- {driver['driver']}: {driver['count']}")
    if not summary.get("top_risk_drivers"):
        lines.append("- No recurring risk drivers identified.")
    return "\n".join(lines).rstrip() + "\n"


def render_customer_adoption_risk_index_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _risk_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    dimension_scores = {
        "target_user_clarity": _inverse_presence_score(_first(unit, metadata, "specific_user", "target_users", "target_user")),
        "workflow_specificity": _inverse_presence_score(_first(unit, metadata, "workflow_context", "workflow")),
        "buyer_strength": _inverse_presence_score(_first(unit, metadata, "buyer", "economic_buyer")),
        "validation_evidence": _inverse_presence_score(_first(unit, metadata, "validation_plan", "evidence", "customer_validation")),
        "onboarding_complexity": _risk_score(_first(unit, metadata, "onboarding_complexity", "implementation_effort")),
        "pricing_friction": _risk_score(_first(unit, metadata, "pricing_friction", "pricing_risk")),
        "support_readiness": _readiness_risk(_first(unit, metadata, "support_readiness", "support_model")),
    }
    score = round(sum(dimension_scores.values()) / len(dimension_scores), 1)
    severity = _severity(score)
    drivers = [_label(key) for key, value in sorted(dimension_scores.items(), key=lambda item: (-item[1], item[0])) if value >= 60][:3]
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "severity": severity,
        "total_risk_score": score,
        "dimension_scores": dimension_scores,
        "risk_drivers": drivers,
        "recommended_mitigation": _mitigation(severity, drivers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {severity: sum(1 for row in rows if row["severity"] == severity) for severity in ("high", "medium", "low")}
    drivers = Counter(driver for row in rows for driver in row["risk_drivers"])
    return {
        "idea_count": len(rows),
        "average_risk_score": round(sum(row["total_risk_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "severity_counts": counts,
        "top_risk_drivers": [{"driver": driver, "count": count} for driver, count in sorted(drivers.items(), key=lambda item: (-item[1], item[0]))[:5]],
    }


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _first(unit: Any, metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metadata:
            return metadata[key]
        value = getattr(unit, key, None) if key in getattr(unit, "__dict__", {}) else None
        if value not in (None, ""):
            return value
    return None


def _inverse_presence_score(value: Any) -> float:
    text = _text(value)
    if not text:
        return 85.0
    if len(text.split()) < 2:
        return 55.0
    return 15.0


def _risk_score(value: Any) -> float:
    text = _text(value).lower()
    if not text:
        return 40.0
    if any(word in text for word in ("high", "complex", "manual", "enterprise", "custom", "blocked")):
        return 80.0
    if any(word in text for word in ("medium", "some", "partial")):
        return 55.0
    if any(word in text for word in ("low", "simple", "none", "ready")):
        return 15.0
    return 45.0


def _readiness_risk(value: Any) -> float:
    text = _text(value).lower()
    if not text:
        return 70.0
    if any(word in text for word in ("ready", "staffed", "documented")):
        return 15.0
    if any(word in text for word in ("partial", "draft")):
        return 50.0
    return 70.0


def _severity(score: float) -> str:
    return "high" if score >= 70 else "medium" if score >= 40 else "low"


def _label(key: str) -> str:
    return key.replace("_", " ").title()


def _mitigation(severity: str, drivers: list[str]) -> str:
    if not drivers:
        return "Keep adoption evidence current through launch."
    action = "Assign an owner and launch mitigation for" if severity == "high" else "Add a planning checkpoint for"
    return f"{action} {drivers[0].lower()}."


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, dict):
        return " ".join(str(value[key]) for key in sorted(value) if str(value[key]).strip())
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
