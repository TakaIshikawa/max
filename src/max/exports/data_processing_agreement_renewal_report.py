"""Data processing agreement renewal export report."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.data_processing_agreement_renewal_report.v1"
KIND = "max.data_processing_agreement_renewal_report"

_ORDER = {"overdue": 0, "due_30": 1, "due_90": 2, "current": 3, "unknown": 4}


def build_data_processing_agreement_renewal_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_row(unit, today) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_ORDER[row["renewal_bucket"]], row["renewal_date"] or "9999-12-31", row["party"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "data_processing_agreement_renewal_report", "domain_filter": domain},
        "summary": _summary(rows),
        "agreement_rows": rows,
        "owner_actions": _owner_actions(rows),
    }


def render_data_processing_agreement_renewal_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_data_processing_agreement_renewal_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Data Processing Agreement Renewal Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Owner Renewal Actions", ""]
    if report.get("owner_actions"):
        for row in report["owner_actions"]:
            lines.append(f"- {row['owner']}: {row['action_count']} agreement(s) need renewal action.")
    else:
        lines.append("- No renewal actions required.")
    lines.extend(["", "## Agreements", ""])
    if report.get("agreement_rows"):
        lines.extend(["| Party | Jurisdiction | Renewal | Bucket | Risk | Owner |", "|-------|--------------|---------|--------|------|-------|"])
        for row in report["agreement_rows"]:
            lines.append(f"| {_md(row['party'])} | {_md(row['jurisdiction'])} | {row['renewal_date'] or ''} | {row['renewal_bucket']} | {row['renewal_risk']} | {_md(row['owner'])} |")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any, today: date) -> dict[str, Any]:
    m = _metadata(unit)
    renewal = _parse_date(m.get("renewal_date") or m.get("dpa_renewal_date"))
    exposure = _list(m.get("subprocessor_exposure") or m.get("subprocessors"))
    bucket = _bucket(renewal, today)
    risk = "high" if bucket in {"overdue", "due_30"} and exposure else ("medium" if bucket in {"overdue", "due_30", "due_90"} else "low")
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "party": _text(m.get("party") or m.get("customer") or m.get("vendor") or getattr(unit, "title", "Untitled")),
        "party_type": _text(m.get("party_type") or ("vendor" if m.get("vendor") else "customer")),
        "renewal_date": renewal.isoformat() if renewal else None,
        "jurisdiction": _text(m.get("jurisdiction") or "unknown"),
        "subprocessor_exposure": exposure,
        "owner": _text(m.get("owner") or "Unassigned"),
        "status": _text(m.get("status") or "not started"),
        "renewal_bucket": bucket,
        "renewal_risk": risk,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"agreement_count": len(rows), "bucket_counts": {bucket: sum(1 for row in rows if row["renewal_bucket"] == bucket) for bucket in _ORDER}, "high_risk_count": sum(1 for row in rows if row["renewal_risk"] == "high")}


def _owner_actions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners = sorted({row["owner"] for row in rows if row["renewal_bucket"] in {"overdue", "due_30", "due_90"}}, key=str.lower)
    return [{"owner": owner, "action_count": sum(1 for row in rows if row["owner"] == owner and row["renewal_bucket"] in {"overdue", "due_30", "due_90"})} for owner in owners]


def _bucket(value: date | None, today: date) -> str:
    if value is None:
        return "unknown"
    delta = (value - today).days
    if delta < 0:
        return "overdue"
    if delta <= 30:
        return "due_30"
    if delta <= 90:
        return "due_90"
    return "current"


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


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
