"""Deterministic privacy impact assessment artifacts for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.privacy_impact_assessment.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "privacy_gate",
    "design_source_idea_ids",
    "section",
    "row_type",
    "item_id",
    "title",
    "description",
    "owner",
    "status",
    "severity",
    "priority",
    "data_handling",
    "risk",
    "mitigation",
    "evidence_references",
    "source_fields",
    "source_idea_ids",
    "data_category_ids",
    "mitigation_ids",
    "details",
)

_SENSITIVE_DOMAIN_TERMS = {
    "healthcare": ("health", "healthcare", "hipaa", "patient", "clinical", "medical", "care"),
    "fintech": ("fintech", "finance", "financial", "bank", "payment", "credit", "loan", "insurance"),
    "education": ("education", "student", "school", "teacher", "learning", "course", "academic"),
    "hr": ("hr", "human resources", "employee", "candidate", "recruiting", "payroll", "workforce"),
}

_CATEGORY_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "account_identity",
        "title": "Account and identity data",
        "classification": "personal_data",
        "keywords": ("account", "identity", "user", "buyer", "email", "profile", "login", "oauth"),
        "description": "Names, roles, account identifiers, contact details, and authentication context.",
        "source_fields": ["buyer", "specific_user", "workflow_context"],
        "owner": "Product owner",
    },
    {
        "id": "workflow_content",
        "title": "Workflow content",
        "classification": "customer_or_user_content",
        "keywords": ("workflow", "record", "document", "ticket", "case", "content", "handoff", "review"),
        "description": "Customer or user-provided records, work items, documents, messages, and decisions.",
        "source_fields": ["workflow_context", "merged_product_concept", "mvp_scope"],
        "owner": "Product owner",
    },
    {
        "id": "regulated_sensitive_data",
        "title": "Regulated or sensitive data",
        "classification": "sensitive_personal_data",
        "keywords": (
            "hipaa",
            "patient",
            "medical",
            "financial",
            "payment",
            "student",
            "employee",
            "candidate",
            "pii",
            "personal",
            "regulated",
        ),
        "description": "Domain-specific sensitive data that may require heightened notice, consent, access, or legal review.",
        "source_fields": ["domain", "theme", "risks", "domain_risks"],
        "owner": "Privacy owner",
    },
    {
        "id": "telemetry_and_usage",
        "title": "Telemetry and usage data",
        "classification": "operational_metadata",
        "keywords": ("analytics", "telemetry", "usage", "event", "metric", "instrumentation", "log", "audit"),
        "description": "Usage events, audit trails, diagnostics, adoption metrics, and operational logs.",
        "source_fields": ["validation_plan", "mvp_scope", "first_milestones"],
        "owner": "Engineering owner",
    },
    {
        "id": "evidence_and_research",
        "title": "Evidence and research data",
        "classification": "research_or_validation_data",
        "keywords": ("evidence", "interview", "validation", "research", "signal", "insight", "pilot"),
        "description": "Interview notes, validation results, evidence signals, and source idea references.",
        "source_fields": ["validation_plan", "why_this_now", "synthesis_rationale", "evidence_signals"],
        "owner": "Research owner",
    },
    {
        "id": "third_party_data",
        "title": "Third-party and integration data",
        "classification": "shared_or_vendor_processed_data",
        "keywords": ("api", "vendor", "integration", "adapter", "third-party", "github", "slack", "crm"),
        "description": "Data shared with external services, integration providers, APIs, or customer platforms.",
        "source_fields": ["tech_approach", "suggested_stack", "mvp_scope", "risks"],
        "owner": "Security owner",
    },
    {
        "id": "generated_outputs",
        "title": "Generated outputs and derived insights",
        "classification": "derived_data",
        "keywords": ("generate", "generated", "summary", "recommendation", "insight", "analysis", "ai", "agent"),
        "description": "Derived outputs, summaries, recommendations, scores, or transformed workflow artifacts.",
        "source_fields": ["merged_product_concept", "mvp_scope", "synthesis_rationale"],
        "owner": "Product owner",
    },
)

_PURPOSE_CONFIGS: tuple[dict[str, str], ...] = (
    {
        "id": "core_workflow_delivery",
        "title": "Deliver the core workflow",
        "description": "Process the minimum data needed to make the target workflow usable for the named user.",
        "owner": "Product owner",
    },
    {
        "id": "validation_and_research",
        "title": "Validate demand and workflow fit",
        "description": "Use pilot, research, and evidence data to validate scope before broad launch.",
        "owner": "Research owner",
    },
    {
        "id": "security_and_audit",
        "title": "Maintain security, auditability, and abuse prevention",
        "description": "Keep operational logs and controls required to protect users, buyers, and customer environments.",
        "owner": "Security owner",
    },
    {
        "id": "buyer_readiness",
        "title": "Support buyer, procurement, and compliance review",
        "description": "Prepare traceable privacy, legal, security, and procurement answers for the buyer.",
        "owner": "Commercial owner",
    },
)

_MITIGATION_CONFIGS: tuple[dict[str, str], ...] = (
    {
        "id": "M1",
        "title": "Data minimization and purpose limits",
        "owner": "Product owner",
        "action": "Define required, optional, and prohibited data for each MVP workflow before pilot use.",
    },
    {
        "id": "M2",
        "title": "Notice, consent, and customer instructions",
        "owner": "Privacy owner",
        "action": "Confirm user notice, consent, customer instructions, and data processing terms for the pilot context.",
    },
    {
        "id": "M3",
        "title": "Access control and audit trail",
        "owner": "Security owner",
        "action": "Limit access by role and retain audit events for sensitive workflows and administrative actions.",
    },
    {
        "id": "M4",
        "title": "Retention, deletion, and export path",
        "owner": "Engineering owner",
        "action": "Set retention defaults, deletion owner, export path, and exception handling before external launch.",
    },
    {
        "id": "M5",
        "title": "Vendor and integration review",
        "owner": "Security owner",
        "action": "Review third-party processors, APIs, subprocessors, and data transfer paths before customer data flows.",
    },
    {
        "id": "M6",
        "title": "Sensitive data review",
        "owner": "Privacy owner",
        "action": "Route healthcare, financial, education, HR, or otherwise regulated data through a privacy review gate.",
    },
)


def build_design_brief_privacy_impact_assessment(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a privacy impact assessment from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _privacy_context(design_brief, source_ideas)
    data_categories = _data_categories(context, source_idea_ids)
    purposes = _processing_purposes(context, data_categories)
    open_questions = _open_questions(context, data_categories, source_idea_ids)
    mitigations = _mitigations(context, data_categories)
    risk_areas = _risk_areas(context, data_categories, mitigations, open_questions, source_idea_ids)
    launch_gates = _launch_gates(context, data_categories, open_questions, risk_areas)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.privacy_impact_assessment",
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief.get("title") or "Untitled Design Brief",
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
            "buyer": context["buyer"],
            "specific_user": context["specific_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "privacy_gate": _privacy_gate(open_questions, risk_areas),
            "data_category_count": len(data_categories),
            "purpose_count": len(purposes),
            "risk_area_count": len(risk_areas),
            "mitigation_count": len(mitigations),
            "open_question_count": len(open_questions),
            "launch_gate_count": len(launch_gates),
            "sensitive_data_expected": any(
                category["classification"] == "sensitive_personal_data" for category in data_categories
            ),
        },
        "privacy_context": context,
        "data_categories": data_categories,
        "processing_purposes": purposes,
        "risk_areas": risk_areas,
        "mitigations": mitigations,
        "open_questions": open_questions,
        "owners": _owners(),
        "launch_gates": launch_gates,
        "source_ideas": source_ideas,
    }


def render_design_brief_privacy_impact_assessment(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a privacy impact assessment as Markdown, deterministic JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_privacy_impact_assessment_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported privacy impact assessment format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Privacy Impact Assessment: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief['domain'] or 'unspecified'}",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Workflow: {brief['workflow_context']}",
        f"Privacy gate: {summary['privacy_gate']}",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
        "## Data Categories",
        "",
    ]
    for category in report["data_categories"]:
        lines.extend(
            [
                f"### {category['id']}: {category['title']}",
                "",
                f"- Classification: {category['classification']}",
                f"- Owner: {category['owner']}",
                f"- Source fields: {_inline_list(category['source_fields'])}",
                f"- Source ideas: {_inline_ids(category['source_idea_ids'])}",
                f"- Collection status: {category['collection_status']}",
                "",
                category["description"],
                "",
            ]
        )

    lines.extend(["## Processing Purposes", ""])
    for purpose in report["processing_purposes"]:
        lines.extend(
            [
                f"- **{purpose['id']}** ({purpose['owner']}): {purpose['description']}",
                f"  Data categories: {_inline_ids(purpose['data_category_ids'])}",
            ]
        )

    lines.extend(["", "## Privacy Risks", ""])
    for risk in report["risk_areas"]:
        lines.extend(
            [
                f"### {risk['id']}: {risk['title']}",
                "",
                f"- Severity: {risk['severity']}",
                f"- Owner: {risk['owner']}",
                f"- Data categories: {_inline_ids(risk['data_category_ids'])}",
                f"- Mitigations: {_inline_ids(risk['mitigation_ids'])}",
                f"- Source fields: {_inline_list(risk['source_fields'])}",
                "",
                risk["description"],
                "",
            ]
        )

    lines.extend(["## Mitigations", ""])
    for mitigation in report["mitigations"]:
        lines.append(f"- **{mitigation['id']}** ({mitigation['owner']}): {mitigation['action']}")

    lines.extend(["", "## Open Questions", ""])
    if report["open_questions"]:
        for question in report["open_questions"]:
            lines.append(f"- **{question['id']}** ({question['owner']}, {question['priority']}): {question['question']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Launch Gates", ""])
    for gate in report["launch_gates"]:
        lines.extend(
            [
                f"- **{gate['id']}** ({gate['owner']}): {gate['recommendation']}",
                f"  Criteria: {gate['criteria']}",
                f"  Status: {gate['status']}",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_privacy_impact_assessment_csv(report: dict[str, Any]) -> str:
    """Render a privacy impact assessment as deterministic CSV text."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()

    for row in _csv_rows(report):
        writer.writerow(row)

    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category in report.get("data_categories") or []:
        rows.append(
            _csv_row(
                report,
                "data_categories",
                category,
                row_type="data_category",
                title=category.get("title"),
                description=category.get("description"),
                owner=category.get("owner"),
                status=category.get("collection_status"),
                data_handling=category.get("classification"),
                evidence_references=_evidence_references(report),
                source_fields=category.get("source_fields"),
                source_idea_ids=category.get("source_idea_ids"),
                details={
                    "classification": category.get("classification", ""),
                },
            )
        )

    for purpose in report.get("processing_purposes") or []:
        rows.append(
            _csv_row(
                report,
                "processing_purposes",
                purpose,
                row_type="processing_purpose",
                title=purpose.get("title"),
                description=purpose.get("description"),
                owner=purpose.get("owner"),
                data_handling=purpose.get("purpose_limit"),
                evidence_references=_evidence_references(report),
                source_fields=purpose.get("source_fields"),
                data_category_ids=purpose.get("data_category_ids"),
                details={
                    "purpose_limit": purpose.get("purpose_limit", ""),
                },
            )
        )

    rows.extend(_csv_lawful_basis_rows(report))
    rows.extend(_csv_retention_rows(report))
    rows.extend(_csv_vendor_rows(report))
    rows.extend(_csv_user_rights_rows(report))

    for risk in report.get("risk_areas") or []:
        rows.append(
            _csv_row(
                report,
                "residual_risks",
                risk,
                row_type="residual_risk",
                title=risk.get("title"),
                description=risk.get("description"),
                owner=risk.get("owner"),
                severity=risk.get("severity"),
                risk=risk.get("description"),
                evidence_references=_evidence_references(report),
                source_fields=risk.get("source_fields"),
                source_idea_ids=risk.get("source_idea_ids"),
                data_category_ids=risk.get("data_category_ids"),
                mitigation_ids=risk.get("mitigation_ids"),
            )
        )

    for mitigation in report.get("mitigations") or []:
        rows.append(
            _csv_row(
                report,
                "mitigations",
                mitigation,
                row_type="mitigation",
                title=mitigation.get("title"),
                description=mitigation.get("action"),
                owner=mitigation.get("owner"),
                status=mitigation.get("status"),
                mitigation=mitigation.get("action"),
                evidence_references=_evidence_references(report),
                source_fields=mitigation.get("source_fields"),
            )
        )

    for question in report.get("open_questions") or []:
        rows.append(
            _csv_row(
                report,
                "open_questions",
                question,
                row_type="open_question",
                title=question.get("question"),
                description=question.get("question"),
                owner=question.get("owner"),
                priority=question.get("priority"),
                evidence_references=_evidence_references(report),
            )
        )

    for owner in report.get("owners") or []:
        rows.append(
            _csv_row(
                report,
                "owners",
                owner,
                row_type="owner",
                item_id=owner.get("role"),
                title=owner.get("role"),
                description=owner.get("responsibility"),
                owner=owner.get("role"),
            )
        )

    for gate in report.get("launch_gates") or []:
        rows.append(
            _csv_row(
                report,
                "launch_gates",
                gate,
                row_type="launch_gate",
                title=gate.get("recommendation"),
                description=gate.get("criteria"),
                owner=gate.get("owner"),
                status=gate.get("status"),
            )
        )

    rows.extend(_csv_evidence_rows(report))
    return rows


def _csv_lawful_basis_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for purpose in report.get("processing_purposes") or []:
        rows.append(
            _csv_row(
                report,
                "lawful_basis_consent_assumptions",
                purpose,
                row_type="lawful_basis_consent_assumption",
                item_id=f"LB-{purpose.get('id')}",
                title=f"Lawful basis and consent assumption: {purpose.get('title')}",
                description="Confirm lawful basis, notice, consent, and customer instruction assumptions before pilot data flows.",
                owner="Privacy owner",
                status="assumption_pending_privacy_review",
                priority="high",
                data_handling=purpose.get("purpose_limit"),
                mitigation="M2",
                evidence_references=_evidence_references(report),
                source_fields=purpose.get("source_fields"),
                data_category_ids=purpose.get("data_category_ids"),
                mitigation_ids=["M2"],
                details={
                    "lawful_basis_assumption": "customer_instructions_or_contractual_necessity_pending_privacy_review",
                    "consent_assumption": "confirm_notice_consent_or_customer_instruction_before_processing",
                },
            )
        )
    return rows


def _csv_retention_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category in report.get("data_categories") or []:
        rows.append(
            _csv_row(
                report,
                "retention",
                category,
                row_type="retention_control",
                item_id=f"RET-{category.get('id')}",
                title=f"Retention and deletion: {category.get('title')}",
                description="Define retention duration, deletion owner, export path, and exception handling for this data category.",
                owner="Engineering owner",
                status="define_before_pilot",
                priority="high" if category.get("classification") == "sensitive_personal_data" else "medium",
                data_handling=category.get("collection_status"),
                mitigation="M4",
                evidence_references=_evidence_references(report),
                source_fields=category.get("source_fields"),
                source_idea_ids=category.get("source_idea_ids"),
                data_category_ids=[category.get("id")],
                mitigation_ids=["M4"],
            )
        )
    return rows


def _csv_vendor_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    context = report.get("privacy_context") or {}
    category_ids = [category.get("id") for category in report.get("data_categories") or []]
    has_vendor_scope = "third_party_data" in category_ids or any(
        term in str(context.get("source_text") or "") for term in ("api", "vendor", "integration", "third-party", "adapter")
    )
    if not has_vendor_scope:
        return []
    return [
        _csv_row(
            report,
            "vendors_subprocessors",
            {"id": "VSP1"},
            row_type="vendor_subprocessor_review",
            title="Vendor and subprocessor review",
            description="Identify external processors, subprocessors, APIs, transfer paths, and required data processing terms.",
            owner="Security owner",
            status="review_required",
            priority="high",
            data_handling="third_party_or_integration_data_transfer",
            risk="External processing may expose customer, user, workflow, telemetry, or evidence data without recorded review.",
            mitigation="M5",
            evidence_references=_evidence_references(report),
            source_fields=["tech_approach", "suggested_stack", "mvp_scope", "risks"],
            source_idea_ids=(report.get("design_brief") or {}).get("source_idea_ids"),
            data_category_ids=["third_party_data"] if "third_party_data" in category_ids else category_ids,
            mitigation_ids=["M5"],
        )
    ]


def _csv_user_rights_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    category_ids = [category.get("id") for category in report.get("data_categories") or []]
    if not category_ids:
        return []
    return [
        _csv_row(
            report,
            "user_rights_impacts",
            {"id": "URI1"},
            row_type="user_rights_impact",
            title="Access, export, deletion, and correction impacts",
            description="Confirm how users or customer administrators can access, export, correct, delete, or restrict in-scope data.",
            owner="Privacy owner",
            status="assess_before_pilot",
            priority="high",
            data_handling="rights_request_and_admin_workflow_impact",
            mitigation="M2; M4",
            evidence_references=_evidence_references(report),
            source_fields=["workflow_context", "mvp_scope", "validation_plan"],
            source_idea_ids=(report.get("design_brief") or {}).get("source_idea_ids"),
            data_category_ids=category_ids,
            mitigation_ids=["M2", "M4"],
        )
    ]


def _csv_evidence_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    evidence = _evidence_references(report)
    rows: list[dict[str, str]] = []
    for index, reference in enumerate(evidence, 1):
        rows.append(
            _csv_row(
                report,
                "evidence_references",
                {"id": reference},
                row_type="evidence_reference",
                item_id=reference,
                title=reference,
                description="Evidence reference used to support the privacy impact assessment.",
                owner="Research owner",
                status="referenced",
                evidence_references=[reference],
                source_idea_ids=_source_idea_ids_for_evidence(report, reference),
                details={"sequence": index},
            )
        )
    return rows


def _csv_row(
    report: dict[str, Any],
    section: str,
    item: dict[str, Any],
    *,
    item_id: Any = None,
    title: Any = None,
    description: Any = None,
    owner: Any = None,
    status: Any = None,
    severity: Any = None,
    priority: Any = None,
    source_fields: Any = None,
    source_idea_ids: Any = None,
    data_category_ids: Any = None,
    mitigation_ids: Any = None,
    details: dict[str, Any] | None = None,
    row_type: Any = None,
    data_handling: Any = None,
    risk: Any = None,
    mitigation: Any = None,
    evidence_references: Any = None,
) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    summary = report.get("summary") or {}
    values = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "privacy_gate": summary.get("privacy_gate"),
        "design_source_idea_ids": brief.get("source_idea_ids"),
        "section": section,
        "row_type": row_type,
        "item_id": item_id if item_id is not None else item.get("id"),
        "title": title if title is not None else item.get("title"),
        "description": description if description is not None else item.get("description"),
        "owner": owner if owner is not None else item.get("owner"),
        "status": status if status is not None else item.get("status"),
        "severity": severity if severity is not None else item.get("severity"),
        "priority": priority if priority is not None else item.get("priority"),
        "data_handling": data_handling,
        "risk": risk,
        "mitigation": mitigation,
        "evidence_references": evidence_references,
        "source_fields": source_fields if source_fields is not None else item.get("source_fields"),
        "source_idea_ids": source_idea_ids if source_idea_ids is not None else item.get("source_idea_ids"),
        "data_category_ids": data_category_ids if data_category_ids is not None else item.get("data_category_ids"),
        "mitigation_ids": mitigation_ids if mitigation_ids is not None else item.get("mitigation_ids"),
        "details": details or {},
    }
    return {column: _csv_cell(values.get(column)) for column in CSV_COLUMNS}


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids", []), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append({"id": idea_id, "role": source.get("role", "source"), "rank": source.get("rank", 0), "missing": True})
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or ("lead" if idea_id == design_brief.get("lead_idea_id") else "source")
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _privacy_context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    source_text = _joined_source_fields(
        source_ideas,
        (
            "buyer",
            "specific_user",
            "workflow_context",
            "problem",
            "solution",
            "value_proposition",
            "domain_risks",
            "evidence_signals",
            "tech_approach",
            "suggested_stack",
            "domain",
        ),
    )
    risks = _dedupe(_string_list(design_brief.get("risks")) + _field_values(source_ideas, "domain_risks"))
    mvp_scope = _dedupe(_string_list(design_brief.get("mvp_scope")) + _field_values(source_ideas, "mvp_scope"))
    evidence = _dedupe(
        _field_values(source_ideas, "evidence_signals")
        + _field_values(source_ideas, "inspiring_insights")
        + _string_list(design_brief.get("evidence_counts"))
    )
    context = {
        "buyer": _clean(design_brief.get("buyer")) or _first(_field_values(source_ideas, "buyer")) or "unknown buyer",
        "specific_user": (
            _clean(design_brief.get("specific_user"))
            or _first(_field_values(source_ideas, "specific_user"))
            or "target user"
        ),
        "workflow_context": (
            _clean(design_brief.get("workflow_context"))
            or _first(_field_values(source_ideas, "workflow_context"))
            or "target workflow"
        ),
        "domain": _clean(design_brief.get("domain")) or _first(_field_values(source_ideas, "domain")),
        "theme": _clean(design_brief.get("theme")),
        "concept": _clean(design_brief.get("merged_product_concept")) or _clean(design_brief.get("title")),
        "validation_plan": _clean(design_brief.get("validation_plan")),
        "mvp_scope": mvp_scope,
        "risks": risks,
        "evidence": evidence,
        "source_text": " ".join(
            _string_list(
                [
                    design_brief.get("title"),
                    design_brief.get("domain"),
                    design_brief.get("theme"),
                    design_brief.get("buyer"),
                    design_brief.get("specific_user"),
                    design_brief.get("workflow_context"),
                    design_brief.get("why_this_now"),
                    design_brief.get("merged_product_concept"),
                    design_brief.get("synthesis_rationale"),
                    design_brief.get("mvp_scope"),
                    design_brief.get("first_milestones"),
                    design_brief.get("validation_plan"),
                    design_brief.get("risks"),
                    source_text,
                ]
            )
        ).lower(),
    }
    context["sensitive_domain"] = _sensitive_domain(context)
    return context


def _data_categories(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for config in _CATEGORY_CONFIGS:
        include = any(keyword in context["source_text"] for keyword in config["keywords"])
        if config["id"] == "regulated_sensitive_data" and context["sensitive_domain"]:
            include = True
        if config["id"] in {"workflow_content", "telemetry_and_usage", "evidence_and_research"}:
            include = True
        if include:
            categories.append(
                {
                    "id": config["id"],
                    "title": config["title"],
                    "classification": config["classification"],
                    "description": config["description"],
                    "owner": config["owner"],
                    "source_fields": config["source_fields"],
                    "source_idea_ids": source_idea_ids,
                    "collection_status": _collection_status(context, config["id"]),
                }
            )
    return categories


def _processing_purposes(context: dict[str, Any], data_categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    category_ids = [category["id"] for category in data_categories]
    purposes = []
    for config in _PURPOSE_CONFIGS:
        purposes.append(
            {
                **config,
                "data_category_ids": category_ids,
                "source_fields": ["workflow_context", "validation_plan", "buyer", "mvp_scope"],
                "purpose_limit": _purpose_limit(context, config["id"]),
            }
        )
    return purposes


def _risk_areas(
    context: dict[str, Any],
    data_categories: list[dict[str, Any]],
    mitigations: list[dict[str, Any]],
    open_questions: list[dict[str, str]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    category_ids = [category["id"] for category in data_categories]
    mitigation_ids = [mitigation["id"] for mitigation in mitigations]
    risks = [
        {
            "title": "Unbounded collection or secondary use",
            "description": "The MVP may collect more data than required or reuse validation data beyond the stated purpose.",
            "severity": "high" if open_questions else "medium",
            "owner": "Privacy owner",
            "source_fields": ["mvp_scope", "validation_plan", "risks"],
            "data_category_ids": category_ids,
            "mitigation_ids": ["M1", "M2", "M4"],
        },
        {
            "title": "Insufficient access, audit, or retention controls",
            "description": "Customer, workflow, telemetry, or evidence records need clear access boundaries and lifecycle controls.",
            "severity": "medium",
            "owner": "Security owner",
            "source_fields": ["workflow_context", "tech_approach", "mvp_scope"],
            "data_category_ids": category_ids,
            "mitigation_ids": ["M3", "M4"],
        },
    ]
    if context["sensitive_domain"] or "regulated_sensitive_data" in category_ids:
        risks.append(
            {
                "title": "Sensitive or regulated data handling",
                "description": "The domain or source risks indicate heightened obligations for regulated or sensitive personal data.",
                "severity": "high",
                "owner": "Privacy owner",
                "source_fields": ["domain", "theme", "risks", "domain_risks"],
                "data_category_ids": ["regulated_sensitive_data"],
                "mitigation_ids": ["M2", "M3", "M6"],
            }
        )
    if any(term in context["source_text"] for term in ("api", "vendor", "integration", "third-party", "adapter")):
        risks.append(
            {
                "title": "Third-party processor or integration exposure",
                "description": "Integration scope may transfer customer or user data to external processors without a recorded review.",
                "severity": "medium",
                "owner": "Security owner",
                "source_fields": ["tech_approach", "suggested_stack", "mvp_scope", "risks"],
                "data_category_ids": ["third_party_data"] if "third_party_data" in category_ids else category_ids,
                "mitigation_ids": ["M3", "M5"],
            }
        )
    for text in context["risks"]:
        if _privacy_relevant(text):
            risks.append(
                {
                    "title": _risk_title(text),
                    "description": text,
                    "severity": "high",
                    "owner": "Privacy owner",
                    "source_fields": ["risks", "domain_risks"],
                    "data_category_ids": category_ids,
                    "mitigation_ids": mitigation_ids,
                }
            )
    return [{**risk, "id": f"PR{index}", "source_idea_ids": source_idea_ids} for index, risk in enumerate(risks, 1)]


def _mitigations(context: dict[str, Any], data_categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    category_ids = {category["id"] for category in data_categories}
    mitigations = []
    for config in _MITIGATION_CONFIGS:
        if config["id"] == "M5" and "third_party_data" not in category_ids:
            continue
        if config["id"] == "M6" and "regulated_sensitive_data" not in category_ids and not context["sensitive_domain"]:
            continue
        mitigations.append(
            {
                **config,
                "status": "recommended",
                "source_fields": ["workflow_context", "mvp_scope", "risks", "validation_plan"],
            }
        )
    return mitigations


def _open_questions(
    context: dict[str, Any],
    data_categories: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    if context["buyer"] == "unknown buyer":
        questions.append(_question("PQ1", "Who is the buyer or customer instruction owner for privacy decisions?"))
    if context["specific_user"] == "target user":
        questions.append(_question("PQ2", "Which user segment is in scope for notices, permissions, and access controls?"))
    if context["workflow_context"] == "target workflow":
        questions.append(_question("PQ3", "What data enters, leaves, and persists in the target workflow?"))
    if not context["mvp_scope"]:
        questions.append(_question("PQ4", "Which MVP actions require personal, customer, telemetry, or evidence data?"))
    if not context["validation_plan"]:
        questions.append(_question("PQ5", "What pilot or research data can be collected, retained, and reused for validation?"))
    if not context["risks"]:
        questions.append(_question("PQ6", "What privacy, security, compliance, or data-rights risks are known today?"))
    if not source_idea_ids:
        questions.append(_question("PQ7", "Which persisted source ideas or evidence records support the privacy assessment?"))
    if not data_categories:
        questions.append(_question("PQ8", "Which data categories are required, optional, or prohibited?"))
    return questions


def _launch_gates(
    context: dict[str, Any],
    data_categories: list[dict[str, Any]],
    open_questions: list[dict[str, str]],
    risk_areas: list[dict[str, Any]],
) -> list[dict[str, str]]:
    has_sensitive = context["sensitive_domain"] or any(
        category["classification"] == "sensitive_personal_data" for category in data_categories
    )
    blocked = bool(open_questions) or any(risk["severity"] == "high" for risk in risk_areas)
    return [
        _gate(
            "LG1",
            "Complete data map before pilot",
            "Product owner",
            "Every required data category has a purpose, owner, source, and minimization decision.",
            "blocked" if open_questions else "pending",
        ),
        _gate(
            "LG2",
            "Approve notice, consent, and customer instructions",
            "Privacy owner",
            "Privacy owner confirms notices, consent assumptions, and customer data processing instructions.",
            "blocked" if open_questions else "pending",
        ),
        _gate(
            "LG3",
            "Define retention, deletion, export, and audit controls",
            "Engineering owner",
            "Lifecycle controls are implemented or explicitly waived for pilot data.",
            "blocked" if blocked else "pending",
        ),
        _gate(
            "LG4",
            "Review sensitive or regulated data before external launch",
            "Privacy owner",
            "Sensitive or regulated data is prohibited, minimized, or approved with documented controls.",
            "blocked" if has_sensitive else "not_required",
        ),
    ]


def _owners() -> list[dict[str, str]]:
    return [
        {"role": "Product owner", "responsibility": "Own data minimization, purpose limits, and workflow scope."},
        {"role": "Privacy owner", "responsibility": "Approve privacy review, notices, consent, and sensitive data handling."},
        {"role": "Security owner", "responsibility": "Own access controls, audit trails, vendors, and integration review."},
        {"role": "Engineering owner", "responsibility": "Implement retention, deletion, export, and telemetry controls."},
        {"role": "Research owner", "responsibility": "Constrain validation evidence collection and reuse."},
    ]


def _privacy_gate(open_questions: list[dict[str, str]], risk_areas: list[dict[str, Any]]) -> str:
    if open_questions:
        return "needs_privacy_discovery"
    if any(risk["severity"] == "high" for risk in risk_areas):
        return "privacy_review_required"
    return "conditional_pilot_ok"


def _sensitive_domain(context: dict[str, Any]) -> str:
    text = context["source_text"]
    for domain, terms in _SENSITIVE_DOMAIN_TERMS.items():
        if any(term in text for term in terms):
            return domain
    return ""


def _collection_status(context: dict[str, Any], category_id: str) -> str:
    if category_id == "regulated_sensitive_data":
        return "assumed_possible_pending_privacy_review"
    if not context["mvp_scope"]:
        return "unknown_pending_mvp_scope"
    return "expected_for_mvp_or_validation"


def _purpose_limit(context: dict[str, Any], purpose_id: str) -> str:
    if purpose_id == "validation_and_research" and not context["validation_plan"]:
        return "Do not collect validation data until the validation plan defines allowed data and retention."
    if purpose_id == "buyer_readiness" and context["buyer"] == "unknown buyer":
        return "Limit buyer-facing disclosure until buyer and customer instruction owner are known."
    return "Use only for the stated design brief purpose unless privacy owner approves expansion."


def _gate(gate_id: str, recommendation: str, owner: str, criteria: str, status: str) -> dict[str, str]:
    return {"id": gate_id, "recommendation": recommendation, "owner": owner, "criteria": criteria, "status": status}


def _question(question_id: str, question: str) -> dict[str, str]:
    return {"id": question_id, "question": question, "owner": "Privacy owner", "priority": "high"}


def _privacy_relevant(text: str) -> bool:
    normalized = text.lower()
    terms = ("privacy", "pii", "personal", "customer data", "hipaa", "gdpr", "security", "consent", "regulated")
    return any(term in normalized for term in terms)


def _risk_title(text: str) -> str:
    compacted = _clean(text).rstrip(".")
    if len(compacted) <= 72:
        return compacted
    return compacted[:69].rstrip() + "..."


def _joined_source_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        values.extend(_field_values(source_ideas, field))
    return "; ".join(_dedupe(values))


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return [_clean(item) for item in values if _clean(item)]
    if isinstance(value, dict):
        return [_clean(f"{key}: {item}") for key, item in sorted(value.items()) if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if _clean(value)))


def _first(values: list[str]) -> str:
    return values[0] if values else ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_csv_cell(item) for item in value if _csv_cell(item))
    if isinstance(value, dict):
        if not value:
            return ""
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _clean(value)


def _evidence_references(report: dict[str, Any]) -> list[str]:
    context = report.get("privacy_context") or {}
    evidence = _string_list(context.get("evidence"))
    if evidence:
        return evidence
    brief = report.get("design_brief") or {}
    return _string_list(brief.get("source_idea_ids"))


def _source_idea_ids_for_evidence(report: dict[str, Any], reference: str) -> list[str]:
    matches = []
    for idea in report.get("source_ideas") or []:
        if reference in _string_list(idea.get("evidence_signals")):
            matches.append(str(idea.get("id")))
    return matches or _string_list((report.get("design_brief") or {}).get("source_idea_ids"))


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "`none`"


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"
