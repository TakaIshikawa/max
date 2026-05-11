"""Generate deterministic secrets rotation plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

SCHEMA_VERSION = "max.spec.secrets_rotation_plan.v1"
SECRETS_ROTATION_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.secrets_rotation_plan"
CSV_COLUMNS = ("section", "item_id", "name", "owner", "cadence", "description")


def generate_secrets_rotation_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = _context(tact_spec)
    classes = _secret_classes(ctx["text"])
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": _source(tact_spec), "summary": {"title": ctx["title"], "workflow_context": ctx["workflow"], "secret_class_count": len(classes)}, "secret_classes": classes, "rotation_schedule": [_row("RS1", "standard_rotation", "security_owner", "90 days", "Rotate production secrets at least quarterly and immediately after suspected exposure.")], "validation_steps": [_row("VS1", "post_rotation_validation", "engineering_owner", "each rotation", "Run health checks, integration smoke tests, and credential access verification.")], "rollback_handling": [_row("RB1", "rollback_window", "on_call_owner", "each rotation", "Keep previous credential available only for the approved rollback window.")], "customer_impact": [_row("CI1", "customer_impact_review", "product_owner", "each rotation", "Confirm customer-facing integrations, webhooks, and API access remain uninterrupted.")], "evidence_requirements": [_row("ER1", "rotation_evidence", "security_owner", "each rotation", "Record owner, timestamp, systems rotated, validation result, and rollback decision.")]}


def render_secrets_rotation_plan_markdown(plan: dict[str, Any]) -> str:
    return _markdown(plan, "Secrets Rotation Plan", ("secret_classes", "rotation_schedule", "validation_steps", "rollback_handling", "customer_impact", "evidence_requirements"))


def render_secrets_rotation_plan_csv(plan: dict[str, Any]) -> str:
    return _csv(plan, ("secret_classes", "rotation_schedule", "validation_steps", "rollback_handling", "customer_impact", "evidence_requirements"))


def _secret_classes(text: str) -> list[dict[str, Any]]:
    definitions = [("api_keys", ("api", "openai", "token"), "integration_owner"), ("database_credentials", ("postgres", "mysql", "database", "db"), "database_owner"), ("webhook_secrets", ("webhook", "slack", "stripe"), "integration_owner"), ("cloud_provider_credentials", ("aws", "gcp", "azure", "cloud"), "platform_owner"), ("ci_cd_secrets", ("ci/cd", "github actions", "pipeline", "deploy"), "devops_owner")]
    rows = []
    lowered = text.lower()
    for name, terms, owner in definitions:
        if any(term in lowered for term in terms):
            rows.append(_row(f"SC{len(rows) + 1}", name, owner, "90 days", f"Rotate and validate {name.replace('_', ' ')} implied by the stack."))
    if not rows:
        rows.append(_row("SC1", "application_runtime_secrets", "security_owner", "90 days", "Maintain a baseline rotation plan for application runtime secrets."))
    return rows


def _context(spec: dict[str, Any]) -> dict[str, str]:
    spec = spec if isinstance(spec, dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return {"title": _text(project.get("title")) or "Untitled TactSpec", "workflow": _text(project.get("workflow_context") or project.get("summary")) or "primary workflow", "text": str(spec)}


def _source(spec: dict[str, Any]) -> dict[str, Any]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"system": source.get("system") or "max", "type": source.get("type") or "tact_spec_preview", "idea_id": source.get("idea_id"), "status": source.get("status"), "domain": source.get("domain"), "category": source.get("category"), "tact_spec_schema_version": spec.get("schema_version"), "tact_spec_kind": spec.get("kind")}


def _row(item_id: str, name: str, owner: str, cadence: str, description: str) -> dict[str, str]:
    return {"id": item_id, "name": name, "owner": owner, "cadence": cadence, "description": description}


def _markdown(plan: dict[str, Any], label: str, sections: tuple[str, ...]) -> str:
    title = plan.get("summary", {}).get("title") or "TactSpec"
    lines = [f"# {title} {label}", "", f"- Schema version: {plan.get('schema_version')}", ""]
    for section in sections:
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        for item in plan.get(section, []):
            lines.append(f"- **{item['id']} {item['name']}** ({item['owner']}, {item['cadence']}): {item['description']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _csv(plan: dict[str, Any], sections: tuple[str, ...]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for section in sections:
        for item in plan.get(section, []):
            writer.writerow({"section": section, "item_id": item.get("id"), "name": item.get("name"), "owner": item.get("owner"), "cadence": item.get("cadence"), "description": item.get("description")})
    return output.getvalue()


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
