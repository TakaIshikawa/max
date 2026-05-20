"""Sales-to-success handoff readiness report export."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.sales_handoff_readiness_report.v1"
KIND = "max.sales_handoff_readiness_report"

_READINESS_ORDER = {"blocked": 0, "incomplete": 1, "ready": 2}


def build_sales_handoff_readiness_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    """Build a deterministic sales-to-success handoff readiness export."""
    rows = [_readiness_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_READINESS_ORDER[row["readiness_status"]], row["account"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "sales_handoff_readiness_report", "domain_filter": domain},
        "summary": summary,
        "readiness_rows": rows,
        "recommended_actions": _recommended_actions(rows, summary),
    }


def render_sales_handoff_readiness_report_json(report: dict[str, Any]) -> str:
    """Render the report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_sales_handoff_readiness_report_markdown(report: dict[str, Any]) -> str:
    """Render the report as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Sales Handoff Readiness Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Accounts analyzed: {summary.get('account_count', 0)}",
        f"- Blocked: {summary.get('status_counts', {}).get('blocked', 0)}",
        f"- Incomplete: {summary.get('status_counts', {}).get('incomplete', 0)}",
        f"- Ready: {summary.get('status_counts', {}).get('ready', 0)}",
        "",
        "## Readiness Rows",
        "",
    ]
    if report.get("readiness_rows"):
        lines.extend([
            "| Account | Owner | Stage | Status | Missing Items | Risks | Recommendation |",
            "|---------|-------|-------|--------|---------------|-------|----------------|",
        ])
        for row in report["readiness_rows"]:
            lines.append(
                f"| {_md(row['account'])} | {_md(row['owner'])} | {_md(row['opportunity_stage'])} | "
                f"{row['readiness_status']} | {_md(', '.join(row['missing_items']) or 'None')} | "
                f"{_md(', '.join(row['risk_flags']) or 'None')} | {_md(row['recommendation'])} |"
            )
    else:
        lines.append("- No sales handoff candidates found.")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _readiness_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    handoff_notes = _text(metadata.get("handoff_notes"))
    success_criteria = _list(metadata.get("success_criteria"))
    requirements = _list(metadata.get("technical_requirements") or metadata.get("requirements"))
    buyer_roles = _list(metadata.get("buyer_roles"))
    open_questions = _list(metadata.get("open_questions"))
    risk_flags = _list(metadata.get("risk_flags"))
    missing_items: list[str] = []
    if not handoff_notes:
        missing_items.append("handoff_notes")
    if not success_criteria:
        missing_items.append("success_criteria")
    if not requirements:
        missing_items.append("technical_requirements")
    if not buyer_roles:
        missing_items.append("buyer_roles")
    if risk_flags:
        status = "blocked"
    elif missing_items or open_questions:
        status = "incomplete"
    else:
        status = "ready"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account") or metadata.get("customer") or getattr(unit, "title", "Untitled")),
        "owner": _text(metadata.get("owner")) or "Unassigned",
        "opportunity_stage": _text(metadata.get("opportunity_stage")) or "unknown",
        "readiness_status": status,
        "handoff_notes_present": bool(handoff_notes),
        "success_criteria_count": len(success_criteria),
        "technical_requirements_count": len(requirements),
        "buyer_roles": buyer_roles,
        "open_questions": open_questions,
        "risk_flags": risk_flags,
        "missing_items": missing_items,
        "recommendation": _recommendation(status, missing_items, open_questions, risk_flags),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: sum(1 for row in rows if row["readiness_status"] == status) for status in ("blocked", "incomplete", "ready")}
    return {
        "account_count": len(rows),
        "status_counts": counts,
        "ready_percent": round((counts["ready"] / len(rows)) * 100, 1) if rows else 0.0,
        "missing_item_counts": dict(sorted(Counter(item for row in rows for item in row["missing_items"]).items())),
    }


def _recommended_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Add sales handoff metadata to buildable units before customer success planning."]
    actions: list[str] = []
    if summary["status_counts"]["blocked"]:
        actions.append("Resolve risk flags before transferring blocked accounts to customer success.")
    if summary["status_counts"]["incomplete"]:
        actions.append("Complete missing handoff notes, success criteria, requirements, and buyer roles for incomplete accounts.")
    if any(row["open_questions"] for row in rows):
        actions.append("Close open questions with named owners before kickoff.")
    if not actions:
        actions.append("Proceed with customer success kickoff using the captured handoff package.")
    return actions


def _recommendation(status: str, missing_items: list[str], open_questions: list[str], risk_flags: list[str]) -> str:
    if status == "blocked":
        return f"Do not hand off until risk flags are resolved: {', '.join(risk_flags)}."
    if missing_items:
        return f"Complete missing fields before handoff: {', '.join(missing_items)}."
    if open_questions:
        return "Answer open questions before kickoff."
    return "Ready for customer success handoff."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str) and ("," in value or ";" in value):
        return [_text(item) for item in value.replace(";", ",").split(",") if _text(item)]
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
