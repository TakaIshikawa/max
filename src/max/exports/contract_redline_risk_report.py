"""Contract redline risk report export."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.contract_redline_risk_report.v1"
KIND = "max.contract_redline_risk_report"

_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_contract_redline_risk_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_contract_row(unit, today) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_RISK_ORDER[row["legal_risk_severity"]], -row["legal_risk_score"], row["account"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "contract_redline_risk_report", "domain_filter": domain},
        "summary": summary,
        "contract_rows": rows,
        "risk_topics": _risk_topics(rows),
        "recommended_actions": _recommended_actions(rows, summary),
    }


def render_contract_redline_risk_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_contract_redline_risk_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Contract Redline Risk Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Contracts analyzed: {summary.get('contract_count', 0)}",
        f"- High risk: {summary.get('severity_counts', {}).get('high', 0)}",
        f"- Medium risk: {summary.get('severity_counts', {}).get('medium', 0)}",
        f"- Low risk: {summary.get('severity_counts', {}).get('low', 0)}",
        "",
        "## Contract Rows",
        "",
    ]
    if report.get("contract_rows"):
        lines.extend(["| Account | Stage | Severity | Score | Topics | Blockers | Action |", "|---------|-------|----------|-------|--------|----------|--------|"])
        for row in report["contract_rows"]:
            lines.append(
                f"| {_md(row['account'])} | {_md(row['contract_stage'])} | {row['legal_risk_severity']} | {row['legal_risk_score']:.1f} | "
                f"{_md(', '.join(row['risk_drivers']) or 'None')} | {_md(', '.join(row['blockers']) or 'None')} | {_md(row['recommended_action'])} |"
            )
    else:
        lines.append("- No contract redline records found.")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _contract_row(unit: Any, today: date) -> dict[str, Any]:
    metadata = _metadata(unit)
    redline_count = int(_number(metadata.get("redline_count")) or 0)
    topics = _list(metadata.get("redline_topics"))
    non_standard = _list(metadata.get("non_standard_terms"))
    blockers = _list(metadata.get("blockers"))
    close_date = _parse_date(metadata.get("target_close_date"))
    days_to_close = (close_date - today).days if close_date else None
    score = min(redline_count * 5, 35) + len(topics) * 6 + len(non_standard) * 12 + len(blockers) * 20
    drivers = []
    if redline_count >= 5:
        drivers.append("redline_volume")
    for key, label in (("liability_cap_status", "liability_cap"), ("data_processing_terms", "data_processing"), ("security_terms", "security_terms")):
        value = _text(metadata.get(key)).lower()
        if value and value not in {"standard", "approved", "accepted", "complete", "ok"}:
            score += 15
            drivers.append(label)
    if days_to_close is not None and days_to_close <= 14:
        score += 20
        drivers.append("close_date_pressure")
    if non_standard:
        drivers.append("non_standard_terms")
    if blockers:
        drivers.append("blockers")
    severity = "high" if score >= 70 else "medium" if score >= 30 else "low"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account") or getattr(unit, "title", "Untitled")),
        "contract_stage": _text(metadata.get("contract_stage")) or "unknown",
        "redline_count": redline_count,
        "redline_topics": topics,
        "non_standard_terms": non_standard,
        "liability_cap_status": _text(metadata.get("liability_cap_status")) or "unknown",
        "data_processing_terms": _text(metadata.get("data_processing_terms")) or "unknown",
        "security_terms": _text(metadata.get("security_terms")) or "unknown",
        "legal_owner": _text(metadata.get("legal_owner")) or "Unassigned",
        "target_close_date": close_date.isoformat() if close_date else None,
        "days_to_close": days_to_close,
        "blockers": blockers,
        "legal_risk_score": round(score, 1),
        "legal_risk_severity": severity,
        "risk_drivers": sorted(set(drivers)),
        "recommended_action": _recommended_action(severity, blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"contract_count": len(rows), "severity_counts": {severity: sum(1 for row in rows if row["legal_risk_severity"] == severity) for severity in ("high", "medium", "low")}}


def _risk_topics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        for topic in [*row["redline_topics"], *row["non_standard_terms"], *row["risk_drivers"]]:
            counts[topic] = counts.get(topic, 0) + 1
    return [{"topic": topic, "count": count} for topic, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _recommended_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Capture contract stage, redline topics, term statuses, legal owners, and blockers before legal close review."]
    actions = []
    if summary["severity_counts"]["high"]:
        actions.append("Escalate high-risk contracts to legal and deal leadership.")
    if any(row["blockers"] for row in rows):
        actions.append("Assign owners and dates for legal blockers.")
    if not actions:
        actions.append("Keep redline topics and close-date pressure current through signature.")
    return actions


def _recommended_action(severity: str, blockers: list[str]) -> str:
    if blockers:
        return "Resolve legal blockers before target close."
    if severity == "high":
        return "Schedule legal deal review."
    if severity == "medium":
        return "Confirm fallback positions for open redlines."
    return "Continue standard contract workflow."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(_text(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
