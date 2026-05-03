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

    return _render_design_brief_retention_policy_markdown(policy)


def _render_design_brief_retention_policy_markdown(policy: dict[str, Any]) -> str:
    brief = _dict_value(policy.get("design_brief"))
    summary = _dict_value(policy.get("summary"))
    source = _dict_value(policy.get("source"))
    data_classes = _list_of_dicts(policy.get("data_classes"))
    retention_rules = _list_of_dicts(policy.get("retention_rules"))
    deletion_controls = _list_of_dicts(policy.get("deletion_controls"))
    access_controls = _list_of_dicts(policy.get("access_controls"))
    audit_requirements = _string_list(policy.get("audit_requirements"))
    open_questions = _string_list(policy.get("open_questions"))
    recommended_next_actions = _string_list(policy.get("recommended_next_actions"))

    lines = [
        f"# Retention Policy: {_text(brief.get('title'), 'Untitled design brief')}",
        "",
        f"Schema: `{_text(policy.get('schema_version'), 'unknown')}`",
        f"Design brief: `{_text(brief.get('id') or source.get('id'), 'unknown')}`",
        f"Status: {_text(brief.get('design_status'), 'unknown')}",
        f"Generated at: {_text(source.get('generated_at'), 'unknown')}",
        "",
        "## Policy Summary",
        "",
        f"- Scope: {_text(summary.get('policy_scope'), 'Not specified')}",
        f"- Data categories: {_text(summary.get('data_class_count'), str(len(data_classes)))}",
        f"- Retention windows: {_text(summary.get('retention_rule_count'), str(len(retention_rules)))}",
        f"- Disposal actions: {_text(summary.get('deletion_control_count'), str(len(deletion_controls)))}",
        "- Compliance rationale: Keep enough context for handoff traceability while avoiding indefinite retention.",
        f"- Review cadence: {_review_cadence(policy)}",
        "",
        "## Data Categories",
        "",
        "| Category | Sensitivity | Description | Source Fields |",
        "| --- | --- | --- | --- |",
    ]

    if data_classes:
        for item in data_classes:
            lines.append(
                "| {name} | {sensitivity} | {description} | {source_fields} |".format(
                    name=_table_cell(item.get("name"), _text(item.get("id"), "Unknown category")),
                    sensitivity=_table_cell(item.get("sensitivity"), "unknown"),
                    description=_table_cell(item.get("description")),
                    source_fields=_table_cell(_join_code(item.get("source_fields"), "none")),
                )
            )
    else:
        lines.append("| None | unknown | Not specified | none |")

    lines.extend(["", "## Data Classes", "", "See Data Categories."])

    lines.extend(
        [
            "",
            "## Retention Windows",
            "",
            "| Rule | Data Category | Retention Window | Trigger | Owner | Compliance Rationale |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if retention_rules:
        for rule in retention_rules:
            lines.append(
                "| {rule_id} | {data_class} | {period} | {trigger} | {owner} | {rationale} |".format(
                    rule_id=_table_cell(rule.get("id"), "Unnumbered"),
                    data_class=_table_cell(rule.get("data_class_id")),
                    period=_table_cell(rule.get("retention_period")),
                    trigger=_table_cell(rule.get("deletion_trigger")),
                    owner=_table_cell(rule.get("owner"), "Unassigned"),
                    rationale=_table_cell(rule.get("rationale")),
                )
            )
    else:
        lines.append("| None | Not specified | Not specified | Not specified | Unassigned | Not specified |")

    lines.extend(["", "## Retention Rules", "", "See Retention Windows."])

    lines.extend(
        [
            "",
            "## Disposal Actions",
            "",
            "| Control | Action | Verification |",
            "| --- | --- | --- |",
        ]
    )
    if deletion_controls:
        for control in deletion_controls:
            lines.append(
                "| {control_id} | {action} | {verification} |".format(
                    control_id=_table_cell(control.get("id"), "Unnumbered"),
                    action=_table_cell(control.get("control")),
                    verification=_table_cell(control.get("verification")),
                )
            )
    else:
        lines.append("| None | Not specified | Not specified |")

    lines.extend(["", "## Deletion Controls", "", "See Disposal Actions."])

    lines.extend(["", "## Compliance Rationale", ""])
    rationales = _unique_text(rule.get("rationale") for rule in retention_rules)
    if rationales:
        lines.extend(f"- {rationale}" for rationale in rationales)
    else:
        lines.append("- Not specified")
    lines.extend(["", "## Audit Requirements", ""])
    if audit_requirements:
        lines.extend(f"- {item}" for item in audit_requirements)
    else:
        lines.append("- None")

    lines.extend(["", "## Owners And Review Cadence", ""])
    lines.extend(
        [
            "| Area | Owner | Review Cadence |",
            "| --- | --- | --- |",
        ]
    )
    owner_rows = _owner_rows(retention_rules, access_controls, policy)
    if owner_rows:
        lines.extend(
            f"| {_table_cell(area)} | {_table_cell(owner, 'Unassigned')} | {_table_cell(cadence)} |"
            for area, owner, cadence in owner_rows
        )
    else:
        lines.append("| Policy | Unassigned | Not specified |")

    lines.extend(["", "## Evidence And Source References", ""])
    references = _source_references(policy)
    if references:
        lines.extend(f"- {reference}" for reference in references)
    else:
        lines.append("- None")

    lines.extend(["", "## Open Questions", ""])
    if open_questions:
        lines.extend(f"- {item}" for item in open_questions)
    else:
        lines.append("- None")

    lines.extend(["", "## Recommended Next Actions", ""])
    if recommended_next_actions:
        lines.extend(f"- {item}" for item in recommended_next_actions)
    else:
        lines.append("- None")
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


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return _compact(value) or default
    if isinstance(value, (dict, list)):
        if not value:
            return default
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _compact(value) or default


def _compact(value: Any) -> str:
    return " ".join(str(value).split())


def _join_code(value: Any, default: str) -> str:
    items = _string_list(value)
    return ", ".join(f"`{item}`" for item in items) or default


def _table_cell(value: Any, default: str = "Not specified") -> str:
    return _text(value, default).replace("|", "\\|").replace("\n", " ")


def _review_cadence(policy: dict[str, Any]) -> str:
    summary = _dict_value(policy.get("summary"))
    cadence = _text(summary.get("review_cadence"))
    if cadence:
        return cadence
    if any(
        item.get("data_class_id") == "sensitive_operational_data"
        for item in _list_of_dicts(policy.get("retention_rules"))
    ):
        return "Monthly during validation, then quarterly after archival"
    return "Quarterly during validation, then before archival or policy extension"


def _owner_rows(
    retention_rules: list[dict[str, Any]],
    access_controls: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    cadence = _review_cadence(policy)
    for rule in retention_rules:
        row = (
            f"{_text(rule.get('id'), 'Retention rule')} {_text(rule.get('data_class_id'), 'data category')}",
            _text(rule.get("owner"), "Unassigned"),
            cadence,
        )
        if row not in seen:
            seen.add(row)
            rows.append(row)
    for control in access_controls:
        row = (
            f"Access control {_text(control.get('id'), '')}".strip(),
            _text(control.get("owner"), "Unassigned"),
            cadence,
        )
        if row not in seen:
            seen.add(row)
            rows.append(row)
    return rows


def _source_references(policy: dict[str, Any]) -> list[str]:
    references: list[str] = []
    source = _dict_value(policy.get("source"))
    brief = _dict_value(policy.get("design_brief"))
    if _text(source.get("id")):
        references.append(
            f"Source {_text(source.get('entity_type'), 'entity')}: `{_text(source.get('id'))}`"
        )
    source_idea_ids = _string_list(brief.get("source_idea_ids"))
    if source_idea_ids:
        references.append(f"Source ideas: {_join_code(source_idea_ids, 'none')}")
    for evidence in _list_of_dicts(policy.get("evidence_references")):
        evidence_id = _text(evidence.get("id"), "unknown")
        evidence_type = _text(evidence.get("type"), "evidence")
        summary = _text(evidence.get("summary"), "No summary provided")
        references.append(f"**{evidence_id}** ({evidence_type}): {summary}")
    return _unique_text(references)


def _unique_text(values: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text not in seen:
            seen.add(text)
            items.append(text)
    return items


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
