"""Security review evidence aging export."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.security_review_evidence_aging.v1"
KIND = "max.security_review_evidence_aging"

_STATUS_ORDER = {"overdue": 0, "stale": 1, "pending": 2, "current": 3}


def build_security_review_evidence_aging_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_evidence_row(unit, today) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["evidence_status"]], -(row["days_overdue"] or 0), row["account"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "security_review_evidence_aging", "domain_filter": domain},
        "summary": summary,
        "evidence_rows": rows,
        "overdue_items": [row for row in rows if row["evidence_status"] == "overdue"],
        "remediation_actions": _remediation_actions(rows, summary),
    }


def render_security_review_evidence_aging_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_security_review_evidence_aging_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Security Review Evidence Aging",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Reviews analyzed: {summary.get('review_count', 0)}",
        f"- Overdue: {summary.get('status_counts', {}).get('overdue', 0)}",
        f"- Stale: {summary.get('status_counts', {}).get('stale', 0)}",
        f"- Pending: {summary.get('status_counts', {}).get('pending', 0)}",
        f"- Current: {summary.get('status_counts', {}).get('current', 0)}",
        "",
        "## Evidence Rows",
        "",
    ]
    if report.get("evidence_rows"):
        lines.extend(["| Account | Status | Due | Submitted | Owner | Blockers | Action |", "|---------|--------|-----|-----------|-------|----------|--------|"])
        for row in report["evidence_rows"]:
            lines.append(
                f"| {_md(row['account'])} | {row['evidence_status']} | {row['evidence_due_at'] or ''} | {row['evidence_submitted_at'] or ''} | "
                f"{_md(row['questionnaire_owner'])} | {_md(', '.join(row['blockers']) or 'None')} | {_md(row['recommended_action'])} |"
            )
    else:
        lines.append("- No security review evidence records found.")
    lines.extend(["", "## Remediation Actions", ""])
    for action in report.get("remediation_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _evidence_row(unit: Any, today: date) -> dict[str, Any]:
    metadata = _metadata(unit)
    submitted = _parse_date(metadata.get("evidence_submitted_at"))
    due = _parse_date(metadata.get("evidence_due_at"))
    blockers = _list(metadata.get("blockers"))
    requests = _list(metadata.get("evidence_requests"))
    stale_flag = _bool(metadata.get("stale_evidence"))
    days_overdue = (today - due).days if due and due < today else 0
    age_days = (today - submitted).days if submitted else None
    if blockers or days_overdue > 0:
        status = "overdue"
    elif stale_flag or (age_days is not None and age_days > 90):
        status = "stale"
    elif requests and not submitted:
        status = "pending"
    else:
        status = "current"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account") or getattr(unit, "title", "Untitled")),
        "security_review_status": _text(metadata.get("security_review_status")) or "unknown",
        "evidence_requests": requests,
        "evidence_submitted_at": submitted.isoformat() if submitted else None,
        "evidence_due_at": due.isoformat() if due else None,
        "evidence_age_days": age_days,
        "days_overdue": days_overdue,
        "stale_evidence": stale_flag,
        "questionnaire_owner": _text(metadata.get("questionnaire_owner")) or "Unassigned",
        "reviewer": _text(metadata.get("reviewer")) or "Unassigned",
        "blockers": blockers,
        "evidence_status": status,
        "recommended_action": _recommended_action(status, blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "review_count": len(rows),
        "status_counts": {status: sum(1 for row in rows if row["evidence_status"] == status) for status in ("overdue", "stale", "pending", "current")},
        "overdue_count": sum(1 for row in rows if row["evidence_status"] == "overdue"),
    }


def _remediation_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Capture security evidence requests, due dates, owners, and reviewers before review tracking."]
    actions = []
    if summary["status_counts"]["overdue"]:
        actions.append("Escalate overdue evidence items with questionnaire owners and reviewers.")
    if summary["status_counts"]["stale"]:
        actions.append("Refresh stale evidence before reusing it in active security reviews.")
    if summary["status_counts"]["pending"]:
        actions.append("Set submission dates for pending evidence requests.")
    if not actions:
        actions.append("Maintain current evidence and review cadence.")
    return actions


def _recommended_action(status: str, blockers: list[str]) -> str:
    if status == "overdue" and blockers:
        return "Resolve blockers and submit overdue evidence."
    if status == "overdue":
        return "Submit overdue evidence immediately."
    if status == "stale":
        return "Refresh evidence and reviewer attestation."
    if status == "pending":
        return "Collect requested evidence."
    return "No remediation required."


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "stale"}


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
