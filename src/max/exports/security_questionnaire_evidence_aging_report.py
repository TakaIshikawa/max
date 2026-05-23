"""Security questionnaire evidence aging export report."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.security_questionnaire_evidence_aging_report.v1"
KIND = "max.security_questionnaire_evidence_aging_report"

_ORDER = {"expired": 0, "missing": 1, "aging": 2, "fresh": 3}


def build_security_questionnaire_evidence_aging_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_row(unit, today) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_ORDER[row["age_bucket"]], row["owner"].lower(), row["control_area"].lower(), row["evidence_name"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "security_questionnaire_evidence_aging_report", "domain_filter": domain},
        "summary": _summary(rows),
        "evidence_rows": rows,
        "owner_priorities": _owner_priorities(rows),
    }


def render_security_questionnaire_evidence_aging_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_security_questionnaire_evidence_aging_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Security Questionnaire Evidence Aging Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Owner Renewal Priorities", ""]
    if report.get("owner_priorities"):
        for row in report["owner_priorities"]:
            lines.append(f"- {row['owner']}: {row['priority']} ({row['renewal_count']} renewals)")
    else:
        lines.append("- No questionnaire evidence records found.")
    lines.extend(["", "## Evidence Rows", ""])
    if report.get("evidence_rows"):
        lines.extend(["| Evidence | Area | Owner | Bucket | Expiry | Priority |", "|----------|------|-------|--------|--------|----------|"])
        for row in report["evidence_rows"]:
            lines.append(f"| {_md(row['evidence_name'])} | {_md(row['control_area'])} | {_md(row['owner'])} | {row['age_bucket']} | {row['expires_at'] or ''} | {row['renewal_priority']} |")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any, today: date) -> dict[str, Any]:
    m = _metadata(unit)
    submitted = _parse_date(m.get("submitted_at") or m.get("evidence_date"))
    expires = _parse_date(m.get("expires_at") or m.get("expiry_date"))
    age_days = (today - submitted).days if submitted else None
    bucket = "missing" if not submitted else ("expired" if expires and expires < today else ("aging" if age_days is not None and age_days > 180 else "fresh"))
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "evidence_name": _text(m.get("evidence_name") or getattr(unit, "title", "Untitled")),
        "owner": _text(m.get("owner") or "Unassigned"),
        "control_area": _text(m.get("control_area") or "general"),
        "submitted_at": submitted.isoformat() if submitted else None,
        "expires_at": expires.isoformat() if expires else None,
        "age_days": age_days,
        "age_bucket": bucket,
        "renewal_priority": _priority(bucket),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"evidence_count": len(rows), "bucket_counts": {bucket: sum(1 for row in rows if row["age_bucket"] == bucket) for bucket in ("fresh", "aging", "expired", "missing")}}


def _owner_priorities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners = sorted({row["owner"] for row in rows}, key=str.lower)
    result = []
    for owner in owners:
        items = [row for row in rows if row["owner"] == owner and row["age_bucket"] in {"expired", "missing", "aging"}]
        if items:
            worst = min(items, key=lambda row: _ORDER[row["age_bucket"]])
            result.append({"owner": owner, "renewal_count": len(items), "priority": _priority(worst["age_bucket"])})
    result.sort(key=lambda row: (-row["renewal_count"], row["owner"].lower()))
    return result


def _priority(bucket: str) -> str:
    return {"expired": "renew immediately", "missing": "collect evidence", "aging": "refresh before reuse", "fresh": "monitor"}.get(bucket, "monitor")


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
