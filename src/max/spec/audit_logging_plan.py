"""Generate deterministic audit logging plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

SCHEMA_VERSION = "max.spec.audit_logging_plan.v1"
AUDIT_LOGGING_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.audit_logging_plan"
CSV_COLUMNS = ("section", "item_id", "name", "category", "owner", "cadence", "description", "evidence_references")
_ESCALATION_TERMS = ("compliance", "privacy", "security", "payment", "admin", "data export", "export")


def generate_audit_logging_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = _context(tact_spec)
    events = [_entry("AL1", "workflow_started", "product_event", "engineering_owner", "continuous", f"Record the start of {ctx['workflow']}."), _entry("AL2", "workflow_completed", "product_event", "engineering_owner", "continuous", "Record successful completion and actor id."), _entry("AL3", "configuration_changed", "admin_event", "security_owner", "continuous", "Record privileged configuration or integration changes.")]
    if ctx["elevated"]:
        events.append(_entry("AL4", "sensitive_data_accessed", "compliance_event", "security_owner", "continuous", "Record access, export, payment, privacy, or admin-sensitive data events."))
    for item in events:
        item["evidence_references"] = ctx["evidence_ids"]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": _source(tact_spec, ctx), "summary": {"title": ctx["title"], "workflow_context": ctx["workflow"], "coverage_recommendation": "elevated" if ctx["elevated"] else "standard", "event_count": len(events)}, "auditable_events": events, "actor_coverage": [_entry("AC1", "user_admin_service_actor_coverage", "actors", "security_owner", "quarterly", "Capture user, admin, service account, and integration actor identifiers.")], "log_sinks": [_entry("LS1", "central_audit_log", "sink", "platform_owner", "continuous", "Send immutable audit records to the central log sink.")], "retention": [_entry("RT1", "audit_log_retention", "retention", "compliance_owner", "annual", "Retain audit logs for at least 12 months unless policy requires longer.")], "alerting": [_entry("AR1", "privileged_or_export_alerts", "alert", "on_call_owner", "continuous", "Alert on privileged changes, suspicious exports, and repeated access failures.")], "reviews": [_entry("RV1", "audit_coverage_review", "review", "security_owner", "quarterly", "Review event coverage and sampling exceptions.")], "recommendations": _recommendations(ctx)}


def render_audit_logging_plan_markdown(plan: dict[str, Any]) -> str:
    return _markdown(plan, "Audit Logging Plan", ("auditable_events", "actor_coverage", "log_sinks", "retention", "alerting", "reviews"))


def render_audit_logging_plan_csv(plan: dict[str, Any]) -> str:
    return _csv(plan, ("auditable_events", "actor_coverage", "log_sinks", "retention", "alerting", "reviews"))


def _context(spec: dict[str, Any]) -> dict[str, Any]:
    spec = spec if isinstance(spec, dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    text = str(spec).lower()
    evidence = _evidence_ids(spec)
    return {"title": _text(project.get("title")) or "Untitled TactSpec", "workflow": _text(project.get("workflow_context") or project.get("summary")) or "primary workflow", "elevated": any(term in text for term in _ESCALATION_TERMS), "evidence_ids": evidence}


def _source(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"system": source.get("system") or "max", "type": source.get("type") or "tact_spec_preview", "idea_id": source.get("idea_id"), "status": source.get("status"), "domain": source.get("domain"), "category": source.get("category"), "tact_spec_schema_version": spec.get("schema_version"), "tact_spec_kind": spec.get("kind"), "evidence_reference_count": len(ctx["evidence_ids"])}


def _entry(item_id: str, name: str, category: str, owner: str, cadence: str, description: str) -> dict[str, Any]:
    return {"id": item_id, "name": name, "category": category, "owner": owner, "cadence": cadence, "description": description, "evidence_references": []}


def _recommendations(ctx: dict[str, Any]) -> list[str]:
    if ctx["elevated"]:
        return ["Use elevated audit coverage for compliance, privacy, security, payment, admin, or export-sensitive workflows."]
    return ["Apply standard audit coverage and revisit if regulated data or admin actions are added."]


def _markdown(plan: dict[str, Any], label: str, sections: tuple[str, ...]) -> str:
    title = plan.get("summary", {}).get("title") or "TactSpec"
    lines = [f"# {title} {label}", "", f"- Schema version: {plan.get('schema_version')}", ""]
    for section in sections:
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        for item in plan.get(section, []):
            lines.append(f"- **{item['id']} {item['name']}** ({item['owner']}): {item['description']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _csv(plan: dict[str, Any], sections: tuple[str, ...]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for section in sections:
        for item in plan.get(section, []):
            writer.writerow({"section": section, "item_id": item.get("id"), "name": item.get("name"), "category": item.get("category"), "owner": item.get("owner"), "cadence": item.get("cadence"), "description": item.get("description"), "evidence_references": "; ".join(item.get("evidence_references") or [])})
    return output.getvalue()


def _evidence_ids(spec: dict[str, Any]) -> list[str]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    return sorted(str(key) for key in evidence)


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
