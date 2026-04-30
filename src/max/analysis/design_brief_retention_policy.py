"""Retention policy exports for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.retention_policy.v1"


def build_design_brief_retention_policy(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic retention policy from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    generated_at = design_brief.get("updated_at") or design_brief.get("created_at")
    data_classes = _data_classes(design_brief)
    retention_rules = _retention_rules(data_classes)
    deletion_controls = _deletion_controls(data_classes)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.retention_policy",
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": generated_at,
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": _string_list(design_brief.get("source_idea_ids")),
        },
        "summary": {
            "policy_scope": _policy_scope(design_brief),
            "data_class_count": len(data_classes),
            "retention_rule_count": len(retention_rules),
            "deletion_control_count": len(deletion_controls),
            "audit_requirement_count": 3,
        },
        "data_classes": data_classes,
        "retention_rules": retention_rules,
        "access_controls": _access_controls(design_brief),
        "deletion_controls": deletion_controls,
        "audit_requirements": _audit_requirements(),
        "open_questions": _open_questions(design_brief),
        "recommended_next_actions": _recommended_next_actions(design_brief),
    }


def render_design_brief_retention_policy(
    policy: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    """Render a retention policy as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(policy, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported retention policy format: {fmt}")

    brief = policy["design_brief"]
    lines = [
        f"# Retention Policy: {brief['title']}",
        "",
        f"Schema: `{policy['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Scope: {policy['summary']['policy_scope']}",
        "",
        "## Data Classes",
        "",
    ]
    for item in policy["data_classes"]:
        lines.extend(
            [
                f"### {item['name']}",
                "",
                item["description"],
                "",
                f"- Sensitivity: `{item['sensitivity']}`",
                f"- Source fields: {', '.join(f'`{field}`' for field in item['source_fields'])}",
                "",
            ]
        )

    lines.extend(["## Retention Rules", ""])
    for rule in policy["retention_rules"]:
        lines.extend(
            [
                f"- **{rule['id']}** keeps `{rule['data_class_id']}` for {rule['retention_period']}.",
                f"  Deletion trigger: {rule['deletion_trigger']}",
                f"  Owner: {rule['owner']}",
                f"  Rationale: {rule['rationale']}",
            ]
        )

    lines.extend(["", "## Deletion Controls", ""])
    lines.extend(
        f"- **{control['id']}**: {control['control']} ({control['verification']})"
        for control in policy["deletion_controls"]
    )

    lines.extend(["", "## Audit Requirements", ""])
    lines.extend(f"- {item}" for item in policy["audit_requirements"])

    lines.extend(["", "## Open Questions", ""])
    lines.extend(f"- {item}" for item in policy["open_questions"])

    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in policy["recommended_next_actions"])
    return "\n".join(lines).rstrip() + "\n"


def retention_policy_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-retention-policy.{extension}"


def _data_classes(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    classes = [
        {
            "id": "design_brief_record",
            "name": "Design brief record",
            "description": "Persisted product concept, source relationships, readiness, risks, and handoff fields.",
            "source_fields": [
                "title",
                "merged_product_concept",
                "mvp_scope",
                "risks",
                "validation_plan",
            ],
            "sensitivity": "internal",
        },
        {
            "id": "evidence_references",
            "name": "Evidence references",
            "description": "Signal and insight identifiers used to support the design brief.",
            "source_fields": ["source_idea_ids", "evidence_counts", "sources"],
            "sensitivity": "internal",
        },
    ]
    if _has_value(design_brief.get("specific_user")) or _has_value(design_brief.get("buyer")):
        classes.append(
            {
                "id": "stakeholder_context",
                "name": "Stakeholder context",
                "description": "Named buyer, user, workflow, and early customer context captured for validation.",
                "source_fields": [
                    "buyer",
                    "specific_user",
                    "workflow_context",
                    "first_10_customers",
                ],
                "sensitivity": "confidential",
            }
        )
    if _has_sensitive_hint(design_brief):
        classes.append(
            {
                "id": "sensitive_operational_data",
                "name": "Sensitive operational data",
                "description": "Potential customer, telemetry, credential, audit, privacy, or compliance data named by the brief.",
                "source_fields": ["risks", "domain_risks", "tech_approach", "suggested_stack"],
                "sensitivity": "restricted",
            }
        )
    return classes


def _retention_rules(data_classes: list[dict[str, Any]]) -> list[dict[str, str]]:
    periods = {
        "design_brief_record": "24 months after the brief is archived",
        "evidence_references": "24 months after the brief is archived",
        "stakeholder_context": "12 months after the last validation activity",
        "sensitive_operational_data": "90 days after validation unless a compliance owner extends it",
    }
    owners = {
        "design_brief_record": "product owner",
        "evidence_references": "research owner",
        "stakeholder_context": "go-to-market owner",
        "sensitive_operational_data": "security or compliance owner",
    }
    rules = []
    for item in data_classes:
        class_id = item["id"]
        rules.append(
            {
                "id": f"RP{len(rules) + 1}",
                "data_class_id": class_id,
                "retention_period": periods[class_id],
                "deletion_trigger": "brief archived, superseded, or validation stopped",
                "rationale": "Keep enough context for handoff traceability while avoiding indefinite retention.",
                "owner": owners[class_id],
            }
        )
    return rules


def _access_controls(design_brief: dict[str, Any]) -> list[dict[str, str]]:
    owner = "security or compliance owner" if _has_sensitive_hint(design_brief) else "product owner"
    return [
        {
            "id": "AC1",
            "control": "Limit edit access to brief owners and implementation leads.",
            "owner": "product owner",
        },
        {
            "id": "AC2",
            "control": "Require explicit approval before exporting stakeholder or sensitive operational context.",
            "owner": owner,
        },
    ]


def _deletion_controls(data_classes: list[dict[str, Any]]) -> list[dict[str, str]]:
    controls = [
        {
            "id": "DC1",
            "control": "Delete archived brief artifacts from downstream handoff locations when retention expires.",
            "verification": "record deletion timestamp and artifact locations",
        },
        {
            "id": "DC2",
            "control": "Redact stakeholder context before sharing examples outside the project workspace.",
            "verification": "review exported Markdown and JSON before distribution",
        },
    ]
    if any(item["id"] == "sensitive_operational_data" for item in data_classes):
        controls.append(
            {
                "id": "DC3",
                "control": "Purge sensitive operational samples within the restricted retention window.",
                "verification": "security owner signs off on sample deletion",
            }
        )
    return controls


def _audit_requirements() -> list[str]:
    return [
        "Log who generated or downloaded the retention policy artifact.",
        "Record retention owner decisions when policy windows are extended.",
        "Keep deletion evidence linked to the design brief identifier.",
    ]


def _open_questions(design_brief: dict[str, Any]) -> list[str]:
    questions = []
    if not _has_value(design_brief.get("buyer")):
        questions.append("Who is accountable for buyer or stakeholder context retention?")
    if not _has_value(design_brief.get("validation_plan")):
        questions.append("What validation completion event should start the retention clock?")
    if _has_sensitive_hint(design_brief):
        questions.append("Which legal, security, or compliance owner can approve restricted data retention?")
    if not questions:
        questions.append("Confirm whether downstream exports need shorter retention than the source brief.")
    return questions


def _recommended_next_actions(design_brief: dict[str, Any]) -> list[str]:
    actions = [
        "Attach this policy to implementation, validation, and publication handoff artifacts.",
        "Confirm deletion ownership before moving the design brief into build execution.",
    ]
    if _has_sensitive_hint(design_brief):
        actions.insert(0, "Run a security or compliance review before collecting restricted operational data.")
    return actions


def _policy_scope(design_brief: dict[str, Any]) -> str:
    workflow = _clean(design_brief.get("workflow_context")) or "the design brief workflow"
    domain = _clean(design_brief.get("domain")) or "the product domain"
    return f"{workflow} in {domain}"


def _has_sensitive_hint(design_brief: dict[str, Any]) -> bool:
    values: list[str] = []
    for field in ("risks", "domain_risks", "tech_approach", "suggested_stack"):
        values.extend(_string_list(design_brief.get(field)))
    text = " ".join(values).lower()
    return any(
        keyword in text
        for keyword in (
            "audit",
            "compliance",
            "credential",
            "customer data",
            "privacy",
            "security",
            "telemetry",
        )
    )


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return value is not None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
