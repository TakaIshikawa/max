"""Procurement readiness checklist export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.procurement_readiness_checklist.v1"
KIND = "max.procurement_readiness_checklist"

_STATUS_ORDER = {"blocked": 0, "partial": 1, "unknown": 2, "ready": 3}
_DOCUMENT_LABELS = {
    "security_questionnaire_status": "security questionnaire",
    "legal_status": "legal review",
    "dpa_status": "DPA",
    "pricing_approval_status": "pricing approval",
    "integration_requirements": "integration requirements",
    "data_residency_requirements": "data residency requirements",
}


def build_procurement_readiness_checklist_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["readiness_status"]], row["account"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "procurement_readiness_checklist", "domain_filter": domain},
        "checklist_rows": rows,
        "summary": _summary(rows),
        "blocked_items": [row for row in rows if row["readiness_status"] == "blocked"],
        "recommendations": _recommendations(rows),
    }


def render_procurement_readiness_checklist_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_procurement_readiness_checklist_markdown(report: dict[str, Any]) -> str:
    lines = ["# Procurement Readiness Checklist", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Checklist", ""]
    if report.get("checklist_rows"):
        lines.extend(["| Idea | Account | Status | Missing | Owner | Next Step |", "|------|---------|--------|---------|-------|-----------|"])
        for row in report["checklist_rows"]:
            lines.append(f"| {_md(row['title'])} | {_md(row['account'])} | {row['readiness_status']} | {_md(', '.join(row['missing_items']) or 'None')} | {_md(row['owner'])} | {_md(row['next_step'])} |")
    else:
        lines.append("- No procurement readiness metadata available.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    missing = [label for key, label in _DOCUMENT_LABELS.items() if _field_state(metadata.get(key)) in {"missing", "blocked"}]
    unknown = [label for key, label in _DOCUMENT_LABELS.items() if _field_state(metadata.get(key)) == "unknown"]
    required_docs = [label for key, label in _DOCUMENT_LABELS.items() if _field_state(metadata.get(key)) != "ready"]
    status = _readiness_status(missing, unknown, metadata)
    owner = _text(metadata.get("owner") or metadata.get("procurement_owner") or "Unassigned")
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "account": _text(metadata.get("account") or metadata.get("segment") or metadata.get("customer") or "Unknown"),
        "readiness_status": status,
        "missing_items": missing + unknown,
        "required_documents": required_docs,
        "owner": owner,
        "next_step": _next_step(status, owner, missing, unknown),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "item_count": len(rows),
        "status_counts": {status: sum(1 for row in rows if row["readiness_status"] == status) for status in _STATUS_ORDER},
        "blocked_count": sum(1 for row in rows if row["readiness_status"] == "blocked"),
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture procurement status fields before enterprise handoff."]
    if any(row["readiness_status"] == "blocked" for row in rows):
        return ["Resolve blocked procurement documents before forecast commit."]
    if any(row["readiness_status"] in {"partial", "unknown"} for row in rows):
        return ["Close partial and unknown procurement checklist items with named owners."]
    return ["Keep procurement evidence current through contracting."]


def _readiness_status(missing: list[str], unknown: list[str], metadata: dict[str, Any]) -> str:
    if missing:
        return "blocked"
    if unknown and len(unknown) == len(_DOCUMENT_LABELS):
        return "unknown"
    if unknown:
        return "partial"
    if not any(key in metadata for key in _DOCUMENT_LABELS):
        return "unknown"
    return "ready"


def _next_step(status: str, owner: str, missing: list[str], unknown: list[str]) -> str:
    if status == "ready":
        return "Proceed to procurement review."
    items = missing or unknown
    if items:
        return f"{owner} to complete {items[0]}."
    return f"{owner} to confirm procurement requirements."


def _field_state(value: Any) -> str:
    if value is None or value == "":
        return "unknown"
    if isinstance(value, bool):
        return "ready" if value else "missing"
    text = _text(value).lower()
    if any(word in text for word in ("blocked", "missing", "rejected", "failed", "not started")):
        return "blocked"
    if any(word in text for word in ("ready", "approved", "complete", "completed", "signed", "none", "not required")):
        return "ready"
    if any(word in text for word in ("partial", "in progress", "pending", "review")):
        return "unknown"
    return "ready" if text else "unknown"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
