"""Deterministic data governance plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import (
    brief_context,
    design_brief_block,
    first_text,
    join_text,
    list_values,
    source_block,
    text,
)

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.data_governance_plan"
SCHEMA_VERSION = "max.design_brief.data_governance_plan.v1"


def build_design_brief_data_governance_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a deterministic data governance plan from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    data_domains = _data_domains(brief, context)
    governance_controls = _governance_controls(context, data_domains)
    evidence_gaps = _evidence_gaps(context, data_domains, evidence_references)
    open_questions = _open_questions(context, data_domains, evidence_gaps)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "buyer": context["buyer"],
            "specific_user": context["target_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "governance_posture": _governance_posture(evidence_gaps, data_domains),
            "primary_data_owner": context["buyer"],
            "workflow_context": context["workflow_context"],
            "data_domain_count": len(data_domains),
            "governance_control_count": len(governance_controls),
            "evidence_reference_count": len(evidence_references),
            "evidence_gap_count": len(evidence_gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "data_domains": data_domains,
        "governance_controls": governance_controls,
        "evidence_references": evidence_references,
        "evidence_gaps": evidence_gaps,
        "open_questions": open_questions,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_data_governance_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render a data governance plan as deterministic Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported data governance plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Data Governance Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Governance posture: {summary['governance_posture']}",
        f"Primary owner: {summary['primary_data_owner']}",
        "",
        "## Data Domains",
        "",
    ]
    for domain in report["data_domains"]:
        lines.append(
            f"- **{domain['id']} {domain['name']}**: owner: {domain['owner']}; "
            f"classification: {domain['classification']}; retention: {domain['retention_policy']}; "
            f"privacy: {domain['privacy_consideration']}; evidence: {join_text(domain['evidence'], 'none')}"
        )

    lines.extend(["", "## Governance Controls", ""])
    for control in report["governance_controls"]:
        lines.append(
            f"- **{control['id']} {control['name']}**: owner: {control['owner']}; "
            f"acceptance: {control['acceptance_check']}; evidence: {control['evidence']}"
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        lines.extend(
            f"- `{item['id']}` ({item['type']}): {item['description']}"
            for item in report["evidence_references"]
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence Gaps", ""])
    if report["evidence_gaps"]:
        lines.extend(f"- **{gap['id']}**: {gap['description']}" for gap in report["evidence_gaps"])
    else:
        lines.append("- None")

    lines.extend(["", "## Open Questions", ""])
    if report["open_questions"]:
        lines.extend(f"- **{item['id']}**: {item['question']}" for item in report["open_questions"])
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def data_governance_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Data Governance Plan'))}-"
        f"data-governance-plan.{extension}"
    )


def _data_domains(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = context["primary_source_idea_id"]
    scope = context["mvp_scope"]
    domains = [
        {
            "id": "D1",
            "name": "Customer and account identity",
            "classification": "personal_or_customer_data",
            "owner": context["buyer"],
            "source_fields": ["buyer", "specific_user", "workflow_context"],
            "retention_policy": "Keep only for active pilot/account lifecycle plus approved audit window.",
            "privacy_consideration": "Confirm notice, customer instructions, and permitted contact/account attributes.",
            "evidence": [context["buyer"], context["target_user"]],
            "source_idea_id": source_id,
        },
        {
            "id": "D2",
            "name": "Workflow records and operational content",
            "classification": "customer_workflow_content",
            "owner": "Product owner",
            "source_fields": ["workflow_context", "mvp_scope", "merged_product_concept"],
            "retention_policy": "Define record-level retention before pilot data is persisted.",
            "privacy_consideration": "Minimize collected fields to the MVP workflow and separate production from test data.",
            "evidence": [context["workflow_context"], *scope],
            "source_idea_id": source_id,
        },
        {
            "id": "D3",
            "name": "Validation evidence and research notes",
            "classification": "research_evidence",
            "owner": "Research owner",
            "source_fields": ["validation_plan", "evidence_signals", "inspiring_insights"],
            "retention_policy": "Retain until decision review, then archive only summarized non-sensitive findings.",
            "privacy_consideration": "Remove participant identifiers unless explicit research retention is approved.",
            "evidence": context["evidence"] or ["No validation evidence attached"],
            "source_idea_id": source_id,
        },
        {
            "id": "D4",
            "name": "Telemetry, audit, and quality signals",
            "classification": "operational_metadata",
            "owner": "Engineering owner",
            "source_fields": ["first_milestones", "risks", "validation_plan"],
            "retention_policy": "Keep audit logs long enough for support, incident review, and launch acceptance.",
            "privacy_consideration": "Avoid storing content payloads in logs; mask identifiers where practical.",
            "evidence": list_values(brief.get("first_milestones")) or context["evidence"],
            "source_idea_id": source_id,
        },
    ]
    if _contains_any([brief.get("domain"), *context["risks"], *context["evidence"]], ("privacy", "pii", "hipaa", "patient", "payment", "financial", "student", "employee")):
        domains.append(
            {
                "id": "D5",
                "name": "Regulated or sensitive data",
                "classification": "sensitive_or_regulated_data",
                "owner": "Privacy owner",
                "source_fields": ["domain", "risks", "domain_risks"],
                "retention_policy": "Do not retain sensitive fields until legal basis and deletion path are approved.",
                "privacy_consideration": "Route through privacy/security review before real customer data is processed.",
                "evidence": context["risks"] or [text(brief.get("domain"), "regulated domain signal")],
                "source_idea_id": source_id,
            }
        )
    return domains


def _governance_controls(
    context: dict[str, Any], data_domains: list[dict[str, Any]]
) -> list[dict[str, str]]:
    sensitive = any(domain["classification"] == "sensitive_or_regulated_data" for domain in data_domains)
    controls = [
        _control("G1", "Named data owner", context["buyer"], "Confirm one accountable owner for each domain before pilot.", f"{len(data_domains)} domain owner assignments recorded."),
        _control("G2", "Data inventory and minimization", "Product owner", "List required, optional, and prohibited fields for the MVP workflow.", "Every MVP scope item maps to an approved data domain."),
        _control("G3", "Retention and deletion path", "Engineering owner", "Define default retention, deletion trigger, export path, and exception owner.", "Retention policy is documented for every domain."),
        _control("G4", "Access and audit controls", "Security owner", "Restrict workflow data by role and keep auditable administrative events.", "Role matrix and audit events pass launch review."),
        _control("G5", "Evidence traceability", "Research owner", "Link governance assumptions to validation evidence and source ideas.", f"{context['evidence_count']} evidence item(s) reviewed."),
    ]
    if sensitive:
        controls.append(_control("G6", "Privacy review gate", "Privacy owner", "Review regulated data, consent, notices, subprocessors, and transfer paths.", "Privacy owner signs off before live sensitive data processing."))
    return controls


def _control(
    control_id: str, name: str, owner: str, action: str, acceptance_check: str
) -> dict[str, str]:
    return {
        "id": control_id,
        "name": name,
        "owner": owner,
        "action": action,
        "acceptance_check": acceptance_check,
        "evidence": acceptance_check,
    }


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for field in ("validation_plan", "synthesis_rationale", "why_this_now"):
        value = text(brief.get(field))
        if value:
            references.append({"id": f"design_brief.{field}", "type": field, "description": value})
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        idea_id = str(idea["id"])
        for field in ("workflow_context", "domain_risks", "evidence_signals", "tech_approach"):
            value = first_text(idea.get(field))
            if value:
                references.append({"id": f"{idea_id}.{field}", "type": field, "description": value})
    return references


def _evidence_gaps(
    context: dict[str, Any],
    data_domains: list[dict[str, Any]],
    evidence_references: list[dict[str, str]],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for key, description in (
        ("buyer", "No explicit accountable buyer or customer instruction owner is attached."),
        ("workflow_context", "No explicit workflow context is attached for data inventory."),
        ("mvp_scope", "No MVP scope items are attached for required data mapping."),
    ):
        if key in context["fallbacks_used"]:
            gaps.append({"id": f"missing_{key}", "description": description})
    if not evidence_references:
        gaps.append({"id": "missing_evidence_references", "description": "No validation or source evidence references support governance assumptions."})
    if any(domain["classification"] == "sensitive_or_regulated_data" for domain in data_domains) and not _contains_any(context["risks"], ("privacy", "retention", "deletion", "consent")):
        gaps.append({"id": "sensitive_data_review_basis", "description": "Sensitive data is implied, but explicit privacy basis and retention evidence are missing."})
    return gaps


def _open_questions(
    context: dict[str, Any],
    data_domains: list[dict[str, Any]],
    evidence_gaps: list[dict[str, str]],
) -> list[dict[str, str]]:
    questions = [
        ("Q1", f"Which owner approves retention and deletion exceptions for {context['workflow_context']}?"),
        ("Q2", "Which fields are required, optional, and prohibited for the first pilot?"),
        ("Q3", "What audit events prove data access and governance controls are operating?"),
    ]
    if evidence_gaps:
        questions.append(("Q4", "What evidence closes the current governance gaps before launch?"))
    if any(domain["classification"] == "sensitive_or_regulated_data" for domain in data_domains):
        questions.append(("Q5", "What privacy, legal, or security signoff is required before live sensitive data is used?"))
    return [{"id": item_id, "question": question} for item_id, question in questions]


def _governance_posture(
    evidence_gaps: list[dict[str, str]], data_domains: list[dict[str, Any]]
) -> str:
    if any(domain["classification"] == "sensitive_or_regulated_data" for domain in data_domains):
        return "privacy_review_required"
    if evidence_gaps:
        return "governance_discovery_required"
    return "ready_for_pilot_controls"


def _contains_any(values: list[Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(text(value).lower() for value in values)
    return any(needle in haystack for needle in needles)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
