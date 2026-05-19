"""Customer escalation risk report export."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_escalation_risk_report.v1"
KIND = "max.customer_escalation_risk_report"

_TIER_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_SEVERITY_SCORE = {"sev1": 35, "sev2": 25, "critical": 35, "high": 25, "medium": 15, "low": 5}


def build_customer_escalation_risk_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_TIER_ORDER[row["risk_tier"]], -row["escalation_count"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_escalation_risk_report", "domain_filter": domain},
        "escalation_rows": rows,
        "summary": _summary(rows),
        "risk_tiers": _risk_tiers(rows),
        "recommendations": _recommendations(rows),
    }


def render_customer_escalation_risk_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_customer_escalation_risk_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Customer Escalation Risk Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
    ]
    summary = report.get("summary", {})
    lines.extend([
        f"- Accounts reviewed: {summary.get('account_count', 0)}",
        f"- Total escalations: {summary.get('total_escalations', 0)}",
        f"- Open blockers: {summary.get('open_blocker_count', 0)}",
        "",
        "## Escalations",
        "",
    ])
    if report.get("escalation_rows"):
        lines.extend([
            "| Idea | Account | Tier | Escalations | Blockers | Sponsor | Renewal | Owner | Action |",
            "|------|---------|------|-------------|----------|---------|---------|-------|--------|",
        ])
        for row in report["escalation_rows"]:
            lines.append(
                f"| {_md(row['title'])} | {_md(row['account'])} | {row['risk_tier']} | "
                f"{row['escalation_count']} | {_md(', '.join(row['open_blockers']) or 'None')} | "
                f"{_md(row['executive_sponsor_status'])} | {_md(row['renewal_date'] or 'Unknown')} | "
                f"{_md(row['mitigation_owner'])} | {_md(row['recommended_action'])} |"
            )
    else:
        lines.append("- No customer escalation metadata available.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    escalation_count = _int(metadata.get("escalation_count") or metadata.get("escalations"), 0)
    blockers = _list(metadata.get("open_blockers") or metadata.get("blockers"))
    sponsor_status = _text(metadata.get("executive_sponsor_status") or metadata.get("sponsor_status") or "unknown")
    severity = _text(metadata.get("severity") or metadata.get("priority")).lower()
    renewal = _text(metadata.get("renewal_date") or metadata.get("renewal"))
    account_tier = _text(metadata.get("account_tier") or metadata.get("customer_tier") or "standard").lower()
    owner = _text(metadata.get("mitigation_owner") or metadata.get("owner") or "Unassigned")
    score = escalation_count * 12 + len(blockers) * 20 + _sponsor_score(sponsor_status) + _severity_score(severity) + _renewal_score(renewal) + _tier_score(account_tier)
    tier = _risk_tier(score)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "account": _text(metadata.get("account") or metadata.get("customer") or metadata.get("segment") or "Unknown"),
        "account_tier": account_tier,
        "escalation_count": escalation_count,
        "open_blockers": blockers,
        "executive_sponsor_status": sponsor_status,
        "severity": severity or "unknown",
        "renewal_date": renewal,
        "mitigation_owner": owner,
        "risk_score": min(score, 100),
        "risk_tier": tier,
        "recommended_action": _action(tier, owner, blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(rows),
        "total_escalations": sum(row["escalation_count"] for row in rows),
        "open_blocker_count": sum(len(row["open_blockers"]) for row in rows),
        "tier_counts": {tier: sum(1 for row in rows if row["risk_tier"] == tier) for tier in _TIER_ORDER},
    }


def _risk_tiers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["risk_tier"] for row in rows)
    return [{"tier": tier, "count": counts[tier]} for tier in _TIER_ORDER]


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture escalation count, blockers, sponsor status, renewal date, and mitigation owner for customer-facing units."]
    recommendations = []
    if any(row["risk_tier"] == "critical" for row in rows):
        recommendations.append("Run an executive escalation review for critical accounts within one business day.")
    if any(row["mitigation_owner"] == "Unassigned" for row in rows):
        recommendations.append("Assign mitigation owners for escalation rows without an accountable owner.")
    if any(row["open_blockers"] for row in rows):
        recommendations.append("Convert open blockers into dated mitigation tasks before the next account review.")
    if not recommendations:
        recommendations.append("Maintain escalation metadata weekly for customer-facing accounts.")
    return recommendations


def _action(tier: str, owner: str, blockers: list[str]) -> str:
    if tier == "critical":
        return f"{owner} to drive executive mitigation and blocker closure."
    if tier == "high":
        return f"{owner} to publish a customer-facing mitigation plan."
    if blockers:
        return f"{owner} to resolve blockers before renewal planning."
    return "Monitor escalation signals in the next account review."


def _risk_tier(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _sponsor_score(value: str) -> int:
    text = value.lower()
    if any(word in text for word in ("blocked", "missing", "unknown", "none", "unresponsive")):
        return 20
    if any(word in text for word in ("weak", "at risk", "limited")):
        return 12
    if any(word in text for word in ("active", "engaged", "confirmed")):
        return 0
    return 8


def _severity_score(value: str) -> int:
    return max((_SEVERITY_SCORE[word] for word in _SEVERITY_SCORE if word in value), default=0)


def _renewal_score(value: str) -> int:
    if not value:
        return 0
    try:
        days = (date.fromisoformat(value[:10]) - date.today()).days
    except ValueError:
        return 8
    if days < 0:
        return 15
    if days <= 30:
        return 20
    if days <= 90:
        return 10
    return 0


def _tier_score(value: str) -> int:
    if value in {"strategic", "enterprise", "tier_1", "tier1"}:
        return 15
    if value in {"premium", "tier_2", "tier2"}:
        return 8
    return 0


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


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
