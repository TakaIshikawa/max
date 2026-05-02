"""Deterministic legal review checklist artifacts for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any, Mapping

SCHEMA_VERSION = "max.design_brief.legal_review_checklist.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "checklist_category",
    "item",
    "owner_reviewer",
    "jurisdiction_or_policy_area",
    "severity_priority",
    "required_action",
    "status",
    "due_date",
    "evidence_source_references",
)

_SECTION_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "privacy",
        "title": "Privacy",
        "owner": "Privacy counsel",
        "priority": "high",
        "description": "Confirm personal, customer, telemetry, and workflow data use before build or buyer review.",
        "source_fields": ["specific_user", "workflow_context", "risks", "validation_plan"],
    },
    {
        "id": "data_rights",
        "title": "Data Rights",
        "owner": "Product counsel",
        "priority": "high",
        "description": "Confirm rights to collect, process, retain, transform, and reuse data or generated outputs.",
        "source_fields": ["workflow_context", "merged_product_concept", "mvp_scope", "source_idea_ids"],
    },
    {
        "id": "claims_review",
        "title": "Claims Review",
        "owner": "Marketing counsel",
        "priority": "medium",
        "description": "Review customer-facing claims, benchmarks, outcome promises, and regulated assertions.",
        "source_fields": ["title", "why_this_now", "synthesis_rationale", "validation_plan"],
    },
    {
        "id": "contractual_procurement_risks",
        "title": "Contractual / Procurement Risks",
        "owner": "Commercial counsel",
        "priority": "high",
        "description": "Prepare buyer review language for procurement, contracting, support, and risk allocation.",
        "source_fields": ["buyer", "value_proposition", "risks", "design_status"],
    },
    {
        "id": "security_review_handoff",
        "title": "Security Review Handoff",
        "owner": "Security and legal owners",
        "priority": "high",
        "description": "Route security, data protection, and incident-response assumptions into the security review plan.",
        "source_fields": ["tech_approach", "suggested_stack", "risks", "mvp_scope"],
    },
    {
        "id": "oss_licensing",
        "title": "OSS / Licensing",
        "owner": "Engineering counsel",
        "priority": "medium",
        "description": "Confirm open-source, third-party service, dataset, and generated-code license obligations.",
        "source_fields": ["tech_approach", "suggested_stack", "mvp_scope", "first_milestones"],
    },
    {
        "id": "approvals",
        "title": "Approvals",
        "owner": "Product lead",
        "priority": "high",
        "description": "Record legal approval owners, blockers, exceptions, and launch or pilot conditions.",
        "source_fields": ["design_status", "readiness_score", "validation_plan", "risks"],
    },
    {
        "id": "unresolved_legal_questions",
        "title": "Unresolved Legal Questions",
        "owner": "Product counsel",
        "priority": "high",
        "description": "Track unknowns that must be answered before pilot, publication, procurement, or implementation.",
        "source_fields": ["buyer", "specific_user", "workflow_context", "risks", "source_idea_ids"],
    },
)


def generate_design_brief_legal_review_checklist(brief: Mapping[str, Any]) -> dict[str, Any]:
    """Generate a stable legal review checklist from a persisted design brief payload."""
    brief_id = _clean(brief.get("id")) or "unknown-design-brief"
    title = _clean(brief.get("title")) or "Untitled Design Brief"
    source_idea_ids = _string_list(brief.get("source_idea_ids"))
    evidence_references = _evidence_references(brief, source_idea_ids)
    legal_questions = _legal_questions(brief, source_idea_ids)
    sections = _sections(brief, evidence_references, legal_questions)
    checklist_items = [item for section in sections for item in section["items"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "brief_id": brief_id,
        "title": title,
        "summary": {
            "review_gate": _review_gate(brief, legal_questions),
            "section_count": len(sections),
            "item_count": len(checklist_items),
            "open_question_count": len(legal_questions),
            "source_reference_count": len(evidence_references),
        },
        "sections": sections,
        "checklist_items": checklist_items,
        "unresolved_legal_questions": legal_questions,
        "evidence_references": evidence_references,
    }


def render_design_brief_legal_review_checklist(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render a legal review checklist artifact as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "markdown":
        return render_design_brief_legal_review_checklist_markdown(report)
    if fmt == "csv":
        return render_design_brief_legal_review_checklist_csv(report)
    raise ValueError(f"Unsupported legal review checklist format: {fmt}")


def render_design_brief_legal_review_checklist_markdown(report: Mapping[str, Any]) -> str:
    """Render a legal review checklist artifact as stable Markdown."""
    summary = report["summary"]
    lines = [
        f"# Legal Review Checklist: {report['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{report['brief_id']}`",
        f"Review gate: {summary['review_gate']}",
        f"Sections: {summary['section_count']}",
        f"Checklist items: {summary['item_count']}",
        "",
    ]

    for section in report["sections"]:
        lines.extend(
            [
                f"## {section['title']}",
                "",
                section["description"],
                "",
                f"- Owner: {section['owner']}",
                f"- Priority: {section['priority']}",
                f"- Source fields: {_inline_list(section['source_fields'])}",
                "",
            ]
        )
        for item in section["items"]:
            lines.extend(
                [
                    f"### {item['id']}: {item['task']}",
                    "",
                    f"- Owner: {item['owner']}",
                    f"- Priority: {item['priority']}",
                    f"- Evidence references: {_inline_refs(item['evidence_reference_ids'])}",
                    f"- Completion criteria: {item['completion_criteria']}",
                    f"- Source fields: {_inline_list(item['source_fields'])}",
                    "",
                ]
            )

    lines.extend(["## Unresolved Legal Questions", ""])
    if report["unresolved_legal_questions"]:
        for question in report["unresolved_legal_questions"]:
            lines.append(f"- **{question['id']}** ({question['owner']}, {question['priority']}): {question['question']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence References", ""])
    for reference in report["evidence_references"]:
        lines.append(f"- **{reference['id']}** ({reference['type']}): {reference['summary']}")

    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_legal_review_checklist_csv(report: Mapping[str, Any]) -> str:
    """Render a legal review checklist artifact as one CSV row per checklist item."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def legal_review_checklist_filename(design_brief: Mapping[str, Any], *, fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(_clean(design_brief.get('id')) or 'design-brief')}-"
        f"{_filename_part(_clean(design_brief.get('title')) or 'Untitled-Design-Brief')}-legal-review-checklist.{extension}"
    )


def _csv_rows(report: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in report.get("sections") or []:
        for item in section.get("items") or []:
            rows.append(_csv_row(section, item))
    return rows


def _csv_row(section: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, str]:
    row = {
        "checklist_category": section.get("id"),
        "item": item.get("id"),
        "owner_reviewer": item.get("owner") or section.get("owner"),
        "jurisdiction_or_policy_area": item.get("jurisdiction")
        or item.get("policy_area")
        or section.get("title")
        or section.get("id"),
        "severity_priority": item.get("severity") or item.get("priority") or section.get("priority"),
        "required_action": item.get("task"),
        "status": item.get("status"),
        "due_date": item.get("due_date") or item.get("due_at") or item.get("target_date"),
        "evidence_source_references": item.get("evidence_reference_ids") or item.get("source_fields"),
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _sections(
    brief: Mapping[str, Any],
    evidence_references: list[dict[str, str]],
    legal_questions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    evidence_ids = _reference_ids(evidence_references)
    sections = []
    item_number = 1
    for config in _SECTION_CONFIGS:
        raw_items = _section_items(config["id"], brief, evidence_ids, legal_questions)
        items = []
        for raw in raw_items:
            items.append(
                {
                    "id": f"DBLR{item_number}",
                    "owner": config["owner"],
                    "priority": config["priority"],
                    **raw,
                }
            )
            item_number += 1
        sections.append({**config, "items": items})
    return sections


def _section_items(
    section_id: str,
    brief: Mapping[str, Any],
    evidence_ids: list[str],
    legal_questions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    title = _clean(brief.get("title")) or "the design brief"
    user = _clean(brief.get("specific_user")) or "target users"
    buyer = _clean(brief.get("buyer")) or "buyer"
    workflow = _clean(brief.get("workflow_context")) or "the target workflow"
    concept = _clean(brief.get("merged_product_concept")) or title
    validation = _clean(brief.get("validation_plan")) or "the validation plan"
    risks = _string_list(brief.get("risks"))
    scope = _string_list(brief.get("mvp_scope"))
    milestones = _string_list(brief.get("first_milestones"))

    if section_id == "privacy":
        return [
            _item(
                f"Classify personal, customer, telemetry, and workflow data used by {workflow}.",
                "Data categories, collection purpose, consent or notice assumptions, retention, deletion, and sharing boundaries are documented.",
                ["specific_user", "workflow_context", "risks"],
                evidence_ids,
            ),
            _item(
                f"Confirm privacy review requirements for {user} before pilot or procurement use.",
                "Privacy owner records whether DPIA, notice updates, consent language, or customer data processing terms are required.",
                ["specific_user", "buyer", "validation_plan"],
                evidence_ids,
            ),
        ]
    if section_id == "data_rights":
        return [
            _item(
                f"Confirm rights to use inputs, outputs, datasets, and generated artifacts for {concept}.",
                "Permitted data sources, prohibited sources, output ownership, and reuse limits are recorded.",
                ["merged_product_concept", "mvp_scope", "source_idea_ids"],
                evidence_ids,
            ),
            _item(
                "Define retention, deletion, export, and audit expectations for design brief evidence and validation artifacts.",
                "Retention owner accepts record classes, deletion path, export path, and audit log expectations.",
                ["validation_plan", "evidence_counts", "source_idea_ids"],
                evidence_ids,
            ),
        ]
    if section_id == "claims_review":
        return [
            _item(
                f"Review customer-facing claims about {title}, including value, safety, compliance, and performance statements.",
                "Every public, sales, or procurement claim is either evidence-backed, softened, removed, or assigned a validation requirement.",
                ["title", "why_this_now", "synthesis_rationale", "validation_plan"],
                evidence_ids,
            ),
            _item(
                f"Validate that pilot success language matches {validation}.",
                "Success criteria distinguish observed validation evidence from unproven marketing, legal, or regulated claims.",
                ["validation_plan", "readiness_score", "evidence_counts"],
                evidence_ids,
            ),
        ]
    if section_id == "contractual_procurement_risks":
        return [
            _item(
                f"Prepare procurement and contract language for {buyer}.",
                "Terms review covers security exhibits, data processing terms, support commitments, warranties, disclaimers, and approval authority.",
                ["buyer", "value_proposition", "design_status"],
                evidence_ids,
            ),
            _item(
                "Convert legal, procurement, and domain risks into contract positions or launch blockers.",
                "Each material risk has an owner, mitigation, customer-facing position, and accept or block decision.",
                ["risks", "domain_risks"],
                evidence_ids,
            ),
        ]
    if section_id == "security_review_handoff":
        return [
            _item(
                "Hand off data protection, credential, incident-response, and audit assumptions to the security review owner.",
                "Security review plan receives legal constraints for data handling, breach notification, audit logs, access scope, and third-party services.",
                ["tech_approach", "suggested_stack", "risks"],
                evidence_ids,
            ),
            _item(
                "Confirm security review cannot be bypassed before external pilot, publication, or autonomous build assignment.",
                "Launch checklist includes explicit legal and security approval gates with named owners.",
                ["design_status", "mvp_scope", "first_milestones"],
                evidence_ids,
            ),
        ]
    if section_id == "oss_licensing":
        return [
            _item(
                "Inventory open-source packages, third-party APIs, datasets, templates, and generated-code dependencies implied by the MVP.",
                "License inventory captures package/service name, license or terms, usage path, attribution, copyleft, data-use, and redistribution obligations.",
                ["tech_approach", "suggested_stack", "mvp_scope"],
                evidence_ids,
            ),
            _item(
                f"Add license review checkpoints to {', '.join(milestones[:2]) if milestones else 'the first implementation milestones'}.",
                "Engineering owner records dependency review before code or assets are shipped to customers.",
                ["first_milestones", "mvp_scope"],
                evidence_ids,
            ),
        ]
    if section_id == "approvals":
        return [
            _item(
                "Record the legal approval path for pilot, customer preview, procurement packet, and public release.",
                "Approval log names required approvers, approval scope, blockers, exceptions, and date of decision.",
                ["design_status", "readiness_score", "validation_plan"],
                evidence_ids,
            ),
            _item(
                "Define escalation rules when legal review finds unresolved privacy, rights, claims, contract, security, or license risk.",
                "Escalation path includes decision owner, stop criteria, acceptable workaround, and re-review trigger.",
                ["risks", "design_status"],
                evidence_ids,
            ),
        ]
    questions = legal_questions or [
        {
            "id": "LQ0",
            "question": "Confirm no unresolved legal questions remain before launch approval.",
            "owner": "Product counsel",
            "priority": "medium",
        }
    ]
    return [
        _item(
            "Resolve or accept every open legal question before the next external commitment.",
            "Each question has an answer, owner-approved exception, or explicit launch blocker decision.",
            ["buyer", "specific_user", "workflow_context", "risks", "source_idea_ids"],
            evidence_ids,
            question_ids=[question["id"] for question in questions],
        )
    ]


def _item(
    task: str,
    completion_criteria: str,
    source_fields: list[str],
    evidence_reference_ids: list[str],
    *,
    question_ids: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "task": task,
        "completion_criteria": completion_criteria,
        "source_fields": source_fields,
        "evidence_reference_ids": evidence_reference_ids or ["brief:fallback"],
        "status": "pending",
    }
    if question_ids is not None:
        item["question_ids"] = question_ids
    return item


def _legal_questions(brief: Mapping[str, Any], source_idea_ids: list[str]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    if not _clean(brief.get("buyer")):
        questions.append(_question("LQ1", "Who is the buyer or commercial decision maker for contract and procurement review?"))
    if not _clean(brief.get("specific_user")):
        questions.append(_question("LQ2", "Which user segment is in scope for privacy notices, terms, and claims review?"))
    if not _clean(brief.get("workflow_context")):
        questions.append(_question("LQ3", "What workflow, data flow, and customer environment will the legal review cover?"))
    if not _string_list(brief.get("risks")):
        questions.append(_question("LQ4", "What legal, privacy, security, procurement, or licensing risks are known today?"))
    if not source_idea_ids:
        questions.append(_question("LQ5", "Which source ideas or evidence records support legal and claims review?"))
    if not _clean(brief.get("validation_plan")):
        questions.append(_question("LQ6", "What validation evidence is required before making customer-facing claims?"))
    return questions


def _question(item_id: str, question: str) -> dict[str, str]:
    return {"id": item_id, "question": question, "owner": "Product counsel", "priority": "high"}


def _review_gate(brief: Mapping[str, Any], legal_questions: list[dict[str, str]]) -> str:
    readiness = _number(brief.get("readiness_score"))
    status = _clean(brief.get("design_status"))
    if legal_questions:
        return "needs_legal_discovery"
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_legal_review"
    return "needs_design_review"


def _evidence_references(brief: Mapping[str, Any], source_idea_ids: list[str]) -> list[dict[str, str]]:
    references = [
        {"id": f"idea:{idea_id}", "type": "source_idea", "summary": f"Source idea {idea_id}"}
        for idea_id in source_idea_ids
    ]
    risks = _string_list(brief.get("risks"))
    if risks:
        references.append({"id": "brief:risks", "type": "risk_register", "summary": "; ".join(risks[:3])})
    evidence_counts = _evidence_counts(brief)
    if sum(evidence_counts.values()) > 0:
        references.append(
            {
                "id": "brief:evidence_counts",
                "type": "evidence_counts",
                "summary": (
                    f"{evidence_counts['signals']} signal(s), {evidence_counts['insights']} insight(s), "
                    f"{evidence_counts['source_ideas']} source idea reference(s)"
                ),
            }
        )
    validation_plan = _clean(brief.get("validation_plan"))
    if validation_plan:
        references.append({"id": "brief:validation_plan", "type": "validation_plan", "summary": validation_plan})
    if not references:
        references.append(
            {
                "id": "brief:fallback",
                "type": "fallback",
                "summary": "No source ideas, risks, validation plan, or evidence counts were persisted; checklist uses conservative fallback review items.",
            }
        )
    return references


def _evidence_counts(brief: Mapping[str, Any]) -> dict[str, int]:
    raw_counts = brief.get("evidence_counts")
    if isinstance(raw_counts, Mapping):
        return {
            "signals": _count(raw_counts.get("signals")),
            "insights": _count(raw_counts.get("insights")),
            "source_ideas": _count(raw_counts.get("source_ideas")),
        }
    return {
        "signals": len(_string_list(brief.get("evidence_signals") or brief.get("signal_ids"))),
        "insights": len(_string_list(brief.get("inspiring_insights") or brief.get("insight_ids"))),
        "source_ideas": len(_string_list(brief.get("source_idea_ids"))),
    }


def _reference_ids(references: list[dict[str, str]]) -> list[str]:
    return [reference["id"] for reference in references]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, tuple):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, dict):
        items = [f"{key}: {item}" for key, item in sorted(value.items())]
        return [_clean(item) for item in items if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _inline_refs(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "`brief:fallback`"


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        return _csv_join(value)
    if isinstance(value, dict):
        return _csv_join(f"{key}: {item}" for key, item in sorted(value.items()))
    return str(value)


def _csv_join(values: Any, *, separator: str = "; ") -> str:
    return separator.join(text for value in values if (text := _csv_text(value)))


def _filename_part(value: str) -> str:
    return "-".join(part for part in value.replace("/", "-").split() if part)
