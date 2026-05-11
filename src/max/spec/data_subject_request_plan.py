"""Generate deterministic data subject request plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

SCHEMA_VERSION = "max.spec.data_subject_request_plan.v1"
DATA_SUBJECT_REQUEST_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.data_subject_request_plan"
CSV_COLUMNS = ("section", "item_id", "name", "owner", "deadline", "description", "evidence_references")


def generate_data_subject_request_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = _context(tact_spec)
    intake = [_item("DSR1", "Request intake", "support_owner", "same business day", f"Capture access, deletion, correction, and export requests for {ctx['workflow']}.", ctx)]
    verification = [_item("DSR2", "Identity verification", "security_owner", "2 business days", f"Verify the requester before disclosing {ctx['data_scope']}.", ctx)]
    discovery = [_item("DSR3", "Data discovery", "data_owner", "10 business days", f"Search product records, logs, integrations, and evidence tied to {ctx['title']}.", ctx)]
    fulfillment = [_item("DSR4", "Fulfillment package", "privacy_owner", "25 calendar days", "Prepare response, export, deletion confirmation, or correction summary.", ctx)]
    exceptions = [_item("DSR5", "Exception handling", "legal_owner", "before due date", "Document denial, extension, conflicting retention, or security exceptions.", ctx)]
    evidence = [_item("DSR6", "Audit evidence", "privacy_owner", "at closure", "Store request timeline, approvals, response artifact, and verification proof.", ctx)]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": _source(tact_spec, ctx), "summary": {"title": ctx["title"], "workflow_context": ctx["workflow"], "target_user": ctx["target_user"], "request_workflow_count": 6, "risk_note_count": len(ctx["risks"])}, "request_intake": intake, "identity_verification": verification, "data_discovery": discovery, "fulfillment": fulfillment, "exception_handling": exceptions, "audit_evidence": evidence, "risk_notes": ctx["risks"], "evidence_references": ctx["evidence"]}


def render_data_subject_request_plan_markdown(plan: dict[str, Any]) -> str:
    title = plan.get("summary", {}).get("title") or "TactSpec"
    lines = [f"# {title} Data Subject Request Plan", "", f"- Schema version: {plan.get('schema_version')}", f"- Source idea ID: {plan.get('source', {}).get('idea_id') or 'none'}", ""]
    for section in ("request_intake", "identity_verification", "data_discovery", "fulfillment", "exception_handling", "audit_evidence"):
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        for item in plan.get(section, []):
            lines.append(f"- **{item['id']} {item['name']}** ({item['owner']}, {item['deadline']}): {item['description']}")
        if not plan.get(section):
            lines.append("- None")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_data_subject_request_plan_csv(plan: dict[str, Any]) -> str:
    return _csv(plan, ("request_intake", "identity_verification", "data_discovery", "fulfillment", "exception_handling", "audit_evidence"))


def _context(spec: dict[str, Any]) -> dict[str, Any]:
    spec = spec if isinstance(spec, dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    text = _compact({"project": project, "solution": solution, "execution": execution})
    evidence = _evidence(spec)
    risks = _items(execution.get("risks"))
    sensitive = any(word in text.lower() for word in ("email", "customer", "payment", "health", "privacy", "account", "export"))
    if sensitive:
        risks.append("Privacy-sensitive data requires verified requester handling.")
    return {"title": _text(project.get("title")) or "Untitled TactSpec", "workflow": _text(project.get("workflow_context") or project.get("summary")) or "primary workflow", "target_user": _text(project.get("specific_user") or project.get("target_users")) or "primary user", "data_scope": "personal and account data" if sensitive else "submitted workflow data", "risks": sorted(set(risks)), "evidence": evidence}


def _source(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"system": source.get("system") or "max", "type": source.get("type") or "tact_spec_preview", "idea_id": source.get("idea_id"), "status": source.get("status"), "domain": source.get("domain"), "category": source.get("category"), "tact_spec_schema_version": spec.get("schema_version"), "tact_spec_kind": spec.get("kind"), "evidence_reference_count": len(ctx["evidence"])}


def _item(item_id: str, name: str, owner: str, deadline: str, description: str, ctx: dict[str, Any]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "deadline": deadline, "description": description, "evidence_references": [item["id"] for item in ctx["evidence"]]}


def _csv(plan: dict[str, Any], sections: tuple[str, ...]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for section in sections:
        for item in plan.get(section, []):
            writer.writerow({"section": section, "item_id": item.get("id"), "name": item.get("name"), "owner": item.get("owner"), "deadline": item.get("deadline"), "description": item.get("description"), "evidence_references": "; ".join(item.get("evidence_references") or [])})
    return output.getvalue()


def _evidence(spec: dict[str, Any]) -> list[dict[str, str]]:
    raw = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs = []
    for key, value in sorted(raw.items()):
        refs.append({"id": str(key), "type": "evidence", "summary": _text(value)})
    return refs


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""


def _compact(value: Any) -> str:
    return str(value)
