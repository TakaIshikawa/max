"""Deterministic accessibility review artifacts for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.accessibility_review"
SCHEMA_VERSION = "max.design_brief.accessibility_review.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "design_brief_domain",
    "design_brief_theme",
    "design_status",
    "readiness_score",
    "review_gate",
    "row_type",
    "area",
    "criterion",
    "item_id",
    "item_title",
    "owner",
    "status",
    "severity",
    "priority",
    "principle",
    "impact",
    "recommendation",
    "evidence",
    "description_or_check",
    "affected_user_group_ids",
    "wcag_refs",
    "risk_ids",
    "wcag_check_ids",
    "access_needs",
    "validation_method",
    "acceptance_criteria",
    "source_idea_ids",
)

_USER_GROUP_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "visual",
        "name": "Blind, low-vision, and color-sensitive users",
        "access_needs": [
            "Screen reader compatible structure, labels, and live updates.",
            "Sufficient contrast and non-color-only status communication.",
            "Keyboard reachable controls with visible focus indicators.",
        ],
        "keywords": ("dashboard", "visual", "chart", "color", "status", "summary", "report", "review"),
        "owner": "Design owner",
    },
    {
        "id": "motor",
        "name": "Keyboard-only and limited-dexterity users",
        "access_needs": [
            "Full task completion without pointer-only interactions.",
            "Predictable focus order, target size, and cancellation paths.",
            "Low-error controls for repetitive or high-volume workflows.",
        ],
        "keywords": ("workflow", "triage", "approval", "handoff", "form", "queue", "bulk"),
        "owner": "Engineering owner",
    },
    {
        "id": "cognitive",
        "name": "Neurodivergent and cognitive-load-sensitive users",
        "access_needs": [
            "Plain-language instructions, consistent navigation, and recoverable mistakes.",
            "Progressive disclosure for dense decisions, risk reviews, and generated recommendations.",
            "Clear success, error, and next-step states.",
        ],
        "keywords": ("complex", "review", "decision", "risk", "compliance", "recommendation", "agent"),
        "owner": "Product owner",
    },
    {
        "id": "hearing",
        "name": "Deaf and hard-of-hearing users",
        "access_needs": [
            "Captions, transcripts, and text alternatives for audio or video content.",
            "No audio-only alerts for time-sensitive or status-changing events.",
        ],
        "keywords": ("audio", "video", "call", "recording", "meeting", "voice", "webinar"),
        "owner": "Product owner",
    },
)

_WCAG_CHECK_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "WCAG1",
        "principle": "perceivable",
        "wcag_refs": ["1.1.1", "1.3.1", "1.4.1", "1.4.3"],
        "check": "Provide text alternatives, semantic structure, and sufficient contrast for core workflow content.",
        "owner": "Design owner",
    },
    {
        "id": "WCAG2",
        "principle": "operable",
        "wcag_refs": ["2.1.1", "2.4.3", "2.4.7", "2.5.8"],
        "check": "Verify keyboard access, focus order, visible focus, and target sizing for the primary journey.",
        "owner": "Engineering owner",
    },
    {
        "id": "WCAG3",
        "principle": "understandable",
        "wcag_refs": ["3.2.3", "3.3.1", "3.3.2", "3.3.3"],
        "check": "Make navigation, input expectations, errors, and recovery steps consistent and explicit.",
        "owner": "Product owner",
    },
    {
        "id": "WCAG4",
        "principle": "robust",
        "wcag_refs": ["4.1.2", "4.1.3"],
        "check": "Expose component names, roles, states, and status messages to assistive technology.",
        "owner": "Engineering owner",
    },
)


def build_design_brief_accessibility_review(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build an accessibility review report from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _accessibility_context(design_brief, source_ideas)
    evidence = _evidence_references(design_brief, source_ideas, source_idea_ids)
    user_groups = _affected_user_groups(context, source_idea_ids)
    risks = _accessibility_risks(context, user_groups, source_idea_ids)
    checks = _wcag_checks(context, risks, source_idea_ids)
    opportunities = _inclusive_design_opportunities(context, user_groups, source_idea_ids)
    validation_tasks = _validation_tasks(context, risks, checks, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": context["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
            "summary": context["summary"],
            "primary_user": context["primary_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "review_gate": _review_gate(context, risks),
            "affected_user_group_count": len(user_groups),
            "risk_count": len(risks),
            "high_risk_count": sum(1 for risk in risks if risk["severity"] == "high"),
            "wcag_check_count": len(checks),
            "opportunity_count": len(opportunities),
            "validation_task_count": len(validation_tasks),
            "fallbacks_used": context["fallbacks_used"],
        },
        "accessibility_context": context,
        "affected_user_groups": user_groups,
        "accessibility_risks": risks,
        "wcag_oriented_checks": checks,
        "inclusive_design_opportunities": opportunities,
        "validation_tasks": validation_tasks,
        "owners": _owners(),
        "evidence_references": evidence,
        "source_metadata": {
            "source_idea_count": len(source_idea_ids),
            "evidence_reference_count": len(evidence),
            "missing_source_idea_ids": [idea["id"] for idea in source_ideas if idea.get("missing")],
        },
        "source_ideas": source_ideas,
    }


def render_design_brief_accessibility_review(report: dict[str, Any], fmt: str = "json") -> str:
    """Render an accessibility review as deterministic JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported accessibility review format: {fmt}")

    return render_design_brief_accessibility_review_markdown(report)


def render_design_brief_accessibility_review_markdown(report: dict[str, Any]) -> str:
    """Render an accessibility review as stable Markdown."""
    brief = report.get("design_brief") or {}
    summary = report.get("summary") or {}
    lines = [
        f"# Accessibility Review: {_markdown_text(brief.get('title'), 'Untitled design brief')}",
        "",
        f"Schema: `{_markdown_text(report.get('schema_version'), 'unknown')}`",
        f"Kind: `{_markdown_text(report.get('kind'), 'unknown')}`",
        f"Design brief: `{_markdown_text(brief.get('id'), 'unknown')}`",
        f"Status: {_markdown_text(brief.get('design_status'), 'unknown')}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Review gate: {_markdown_text(summary.get('review_gate'), 'unknown')}",
        f"Source ideas: {_markdown_list(brief.get('source_idea_ids'))}",
        "",
        "## Design Brief Summary",
        "",
        f"- Summary: {_markdown_text(brief.get('summary'), 'Not specified')}",
        f"- Primary user: {_markdown_text(brief.get('primary_user'), 'Not specified')}",
        f"- Buyer: {_markdown_text(brief.get('buyer'), 'Not specified')}",
        f"- Workflow: {_markdown_text(brief.get('workflow_context'), 'Not specified')}",
        f"- Fallbacks used: {_markdown_list(summary.get('fallbacks_used'))}",
        "",
        "## Affected User Groups",
        "",
    ]

    groups = _list_of_dicts(report.get("affected_user_groups"))
    if groups:
        for group in groups:
            lines.extend(
                [
                    f"### {_markdown_text(group.get('id'), 'group')}: {_markdown_text(group.get('name'), 'Unnamed group')}",
                    "",
                    f"- Owner: {_markdown_text(group.get('owner'), 'Unassigned')}",
                    f"- Relevance: {_markdown_text(group.get('relevance'), 'Not specified')}",
                    f"- Source ideas: {_markdown_list(group.get('source_idea_ids'))}",
                    "- Access needs:",
                ]
            )
            needs = _string_list(group.get("access_needs"))
            if needs:
                for need in needs:
                    lines.append(f"  - {need}")
            else:
                lines.append("  - None")
            lines.append("")
    else:
        lines.extend(["- None", ""])

    lines.extend(["## Accessibility Risks", ""])
    risks = _list_of_dicts(report.get("accessibility_risks"))
    if risks:
        for risk in risks:
            lines.extend(
                [
                    f"### {_markdown_text(risk.get('id'), 'risk')}: {_markdown_text(risk.get('title'), 'Untitled risk')}",
                    "",
                    f"- Severity: {_markdown_text(risk.get('severity'), 'unknown')}",
                    f"- Owner: {_markdown_text(risk.get('owner'), 'Unassigned')}",
                    f"- Affected user groups: {_markdown_list(risk.get('affected_user_group_ids'))}",
                    f"- WCAG refs: {_markdown_list(risk.get('wcag_refs'))}",
                    f"- Evidence/source ideas: {_markdown_list(risk.get('source_idea_ids'))}",
                    "",
                    _markdown_text(risk.get("description"), "Not specified"),
                    "",
                ]
            )
    else:
        lines.extend(["- None", ""])

    lines.extend(["## WCAG-Oriented Checks", ""])
    checks = _list_of_dicts(report.get("wcag_oriented_checks"))
    if checks:
        for check in checks:
            lines.extend(
                [
                    (
                        f"- **{_markdown_text(check.get('id'), 'WCAG')} "
                        f"{_markdown_text(check.get('principle'), 'principle')}** "
                        f"({_markdown_text(check.get('owner'), 'Unassigned')}): "
                        f"{_markdown_text(check.get('check'), 'Not specified')}"
                    ),
                    f"  WCAG refs: {_markdown_list(check.get('wcag_refs'))}",
                    f"  Validation method: {_markdown_text(check.get('validation_method'), 'Not specified')}",
                    f"  Related risks: {_markdown_list(check.get('risk_ids'))}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Inclusive Design Opportunities", ""])
    opportunities = _list_of_dicts(report.get("inclusive_design_opportunities"))
    if opportunities:
        for opportunity in opportunities:
            lines.extend(
                [
                    (
                        f"- **{_markdown_text(opportunity.get('id'), 'opportunity')} "
                        f"{_markdown_text(opportunity.get('title'), 'Untitled opportunity')}** "
                        f"({_markdown_text(opportunity.get('owner'), 'Unassigned')}): "
                        f"{_markdown_text(opportunity.get('opportunity'), 'Not specified')}"
                    ),
                    f"  Expected benefit: {_markdown_text(opportunity.get('expected_benefit'), 'Not specified')}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Validation Tasks", ""])
    tasks = _list_of_dicts(report.get("validation_tasks"))
    if tasks:
        for task in tasks:
            lines.extend(
                [
                    (
                        f"- **{_markdown_text(task.get('id'), 'task')} "
                        f"{_markdown_text(task.get('task'), 'Untitled task')}** "
                        f"({_markdown_text(task.get('owner'), 'Unassigned')}, "
                        f"{_markdown_text(task.get('priority'), 'unknown')}): "
                        f"{_markdown_text(task.get('method'), 'Not specified')}"
                    ),
                    f"  Acceptance criteria: {_markdown_text(task.get('acceptance_criteria'), 'Not specified')}",
                    f"  Evidence/source ideas: {_markdown_list(task.get('source_idea_ids'))}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Owners", ""])
    owners = _list_of_dicts(report.get("owners"))
    if owners:
        for owner in owners:
            lines.append(
                f"- **{_markdown_text(owner.get('role'), 'Owner')}**: {_markdown_text(owner.get('responsibility'), 'Not specified')}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence References", ""])
    evidence = _list_of_dicts(report.get("evidence_references"))
    if evidence:
        for ref in evidence:
            lines.append(
                f"- **{_markdown_text(ref.get('id'), 'reference')}** ({_markdown_text(ref.get('type'), 'unknown')}): {_markdown_text(ref.get('summary'), 'Not specified')}"
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def accessibility_review_filename(design_brief: dict[str, Any], *, fmt: str = "json") -> str:
    """Return a stable filename for an accessibility review export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-accessibility-review.{extension}"
    )


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group in report.get("affected_user_groups") or []:
        rows.append(
            _csv_row(
                report,
                row_type="affected_user_group",
                area="affected_user_group",
                criterion=group.get("name"),
                item_id=group.get("id"),
                item_title=group.get("name"),
                owner=group.get("owner"),
                status=group.get("status"),
                impact=group.get("relevance"),
                recommendation=group.get("access_needs"),
                evidence=group.get("source_idea_ids"),
                description_or_check=group.get("relevance"),
                affected_user_group_ids=[group.get("id")],
                access_needs=group.get("access_needs"),
                source_idea_ids=group.get("source_idea_ids"),
            )
        )
    for risk in report.get("accessibility_risks") or []:
        rows.append(
            _csv_row(
                report,
                row_type="accessibility_risk",
                area="risk",
                criterion=risk.get("title"),
                item_id=risk.get("id"),
                item_title=risk.get("title"),
                owner=risk.get("owner"),
                status=risk.get("status"),
                severity=risk.get("severity"),
                impact=risk.get("description"),
                recommendation=_risk_recommendation(report, risk),
                evidence=_csv_evidence(
                    risk.get("source_idea_ids"),
                    risk.get("affected_user_group_ids"),
                    risk.get("wcag_refs"),
                ),
                description_or_check=risk.get("description"),
                affected_user_group_ids=risk.get("affected_user_group_ids"),
                wcag_refs=risk.get("wcag_refs"),
                source_idea_ids=risk.get("source_idea_ids"),
            )
        )
    for check in report.get("wcag_oriented_checks") or []:
        rows.append(
            _csv_row(
                report,
                row_type="wcag_oriented_check",
                area=check.get("principle"),
                criterion=check.get("check"),
                item_id=check.get("id"),
                item_title=check.get("check"),
                owner=check.get("owner"),
                status=check.get("status"),
                principle=check.get("principle"),
                impact=check.get("risk_ids"),
                recommendation=check.get("validation_method"),
                evidence=_csv_evidence(
                    check.get("source_idea_ids"),
                    check.get("wcag_refs"),
                    check.get("risk_ids"),
                ),
                description_or_check=check.get("check"),
                wcag_refs=check.get("wcag_refs"),
                risk_ids=check.get("risk_ids"),
                validation_method=check.get("validation_method"),
                source_idea_ids=check.get("source_idea_ids"),
            )
        )
    for opportunity in report.get("inclusive_design_opportunities") or []:
        rows.append(
            _csv_row(
                report,
                row_type="inclusive_design_opportunity",
                area="inclusive_design",
                criterion=opportunity.get("title"),
                item_id=opportunity.get("id"),
                item_title=opportunity.get("title"),
                owner=opportunity.get("owner"),
                status=opportunity.get("status"),
                impact=opportunity.get("expected_benefit"),
                recommendation=opportunity.get("opportunity"),
                evidence=_csv_evidence(
                    opportunity.get("source_idea_ids"),
                    opportunity.get("affected_user_group_ids"),
                ),
                description_or_check=opportunity.get("opportunity"),
                affected_user_group_ids=opportunity.get("affected_user_group_ids"),
                source_idea_ids=opportunity.get("source_idea_ids"),
            )
        )
    for task in report.get("validation_tasks") or []:
        rows.append(
            _csv_row(
                report,
                row_type="validation_task",
                area="validation",
                criterion=task.get("task"),
                item_id=task.get("id"),
                item_title=task.get("task"),
                owner=task.get("owner"),
                status=task.get("status"),
                priority=task.get("priority"),
                impact=task.get("acceptance_criteria"),
                recommendation=task.get("method"),
                evidence=_csv_evidence(
                    task.get("source_idea_ids"),
                    task.get("risk_ids"),
                    task.get("wcag_check_ids"),
                ),
                description_or_check=task.get("method"),
                risk_ids=task.get("risk_ids"),
                wcag_check_ids=task.get("wcag_check_ids"),
                acceptance_criteria=task.get("acceptance_criteria"),
                source_idea_ids=task.get("source_idea_ids"),
            )
        )
    return rows


def _csv_row(report: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    summary = report.get("summary") or {}
    row = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "design_brief_domain": brief.get("domain"),
        "design_brief_theme": brief.get("theme"),
        "design_status": brief.get("design_status"),
        "readiness_score": brief.get("readiness_score"),
        "review_gate": summary.get("review_gate"),
        **values,
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _risk_recommendation(report: dict[str, Any], risk: dict[str, Any]) -> str:
    gate = (report.get("summary") or {}).get("review_gate")
    owner = risk.get("owner")
    if gate and owner:
        return f"{owner} to resolve or explicitly accept before {gate}."
    if owner:
        return f"{owner} to resolve or explicitly accept."
    return ""


def _csv_evidence(*values: Any) -> str:
    return _csv_join(values)


def _csv_join(values: Any, *, separator: str = "; ") -> str:
    return separator.join(text for value in _csv_values(values) if (text := _csv_text(value)))


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        return _csv_join(value)
    return str(value)


def _csv_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in sorted(value.items())]
    if isinstance(value, list | tuple | set):
        values: list[Any] = []
        for item in value:
            values.extend(_csv_values(item))
        return values
    return [value]


def _accessibility_context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    fallbacks: list[str] = []
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    primary_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        ("target users", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("product owner", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    product_concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        f"{title} product concept",
    )
    validation_plan = _first_with_label(
        fallbacks,
        "validation_plan",
        (design_brief.get("validation_plan"), "design_brief.validation_plan"),
        (lead_idea and lead_idea.get("validation_plan"), "lead_idea.validation_plan"),
        (_field_values(source_ideas, "validation_plan"), "source_ideas.validation_plan"),
        ("Run accessibility review with representative assistive technology users before implementation handoff.", "explicit_fallback"),
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    if not scope:
        scope = [f"first usable {title} workflow"]
        fallbacks.append("mvp_scope")
    risks = _dedupe_strings([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    if not risks:
        risks = ["Accessibility risks are under-specified; use conservative WCAG checks before implementation."]
        fallbacks.append("risks")
    source_text = " ".join(
        _string_list(
            [
                design_brief.get("title"),
                design_brief.get("domain"),
                design_brief.get("theme"),
                design_brief.get("why_this_now"),
                design_brief.get("merged_product_concept"),
                design_brief.get("mvp_scope"),
                design_brief.get("first_milestones"),
                design_brief.get("validation_plan"),
                design_brief.get("risks"),
                _field_values(source_ideas, "problem"),
                _field_values(source_ideas, "solution"),
                _field_values(source_ideas, "workflow_context"),
                _field_values(source_ideas, "domain_risks"),
            ]
        )
    ).lower()
    return {
        "title": title,
        "summary": _first_text(design_brief.get("merged_product_concept"), lead_idea and lead_idea.get("one_liner"), title),
        "primary_user": primary_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": product_concept,
        "validation_plan": validation_plan,
        "primary_scope": scope[0],
        "scope": scope[:5],
        "risks": risks[:6],
        "source_text": source_text,
        "fallbacks_used": _dedupe_strings(fallbacks),
    }


def _affected_user_groups(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    groups = []
    for config in _USER_GROUP_CONFIGS:
        relevant = any(keyword in context["source_text"] for keyword in config["keywords"])
        if config["id"] in {"visual", "motor", "cognitive"}:
            relevant = True
        if relevant:
            groups.append(
                {
                    "id": config["id"],
                    "name": config["name"],
                    "owner": config["owner"],
                    "access_needs": config["access_needs"],
                    "relevance": _group_relevance(config["id"], context),
                    "source_idea_ids": source_idea_ids,
                }
            )
    return groups


def _accessibility_risks(
    context: dict[str, Any],
    user_groups: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    group_ids = [group["id"] for group in user_groups]
    risks = [
        {
            "title": "Primary workflow may not be keyboard operable",
            "description": f"{context['primary_scope']} must be completable without pointer-only controls or hidden focus states.",
            "severity": "high",
            "owner": "Engineering owner",
            "affected_user_group_ids": [group for group in group_ids if group in {"motor", "visual"}],
            "wcag_refs": ["2.1.1", "2.4.3", "2.4.7"],
        },
        {
            "title": "Generated or dense content may not be perceivable",
            "description": f"{context['product_concept']} may rely on visual hierarchy, color, or generated summaries without semantic alternatives.",
            "severity": "high" if _visual_heavy(context) else "medium",
            "owner": "Design owner",
            "affected_user_group_ids": [group for group in group_ids if group in {"visual", "cognitive"}],
            "wcag_refs": ["1.1.1", "1.3.1", "1.4.1", "1.4.3"],
        },
        {
            "title": "Errors and recommendations may be hard to understand or recover from",
            "description": f"{context['primary_user']} needs clear explanations, validation states, and reversal paths in {context['workflow_context']}.",
            "severity": "medium",
            "owner": "Product owner",
            "affected_user_group_ids": [group for group in group_ids if group in {"cognitive", "motor"}],
            "wcag_refs": ["3.3.1", "3.3.2", "3.3.3"],
        },
    ]
    if "hearing" in group_ids:
        risks.append(
            {
                "title": "Audio or video evidence may lack text alternatives",
                "description": "Meeting, call, audio, or video workflows require captions, transcripts, and non-audio alerts.",
                "severity": "medium",
                "owner": "Product owner",
                "affected_user_group_ids": ["hearing"],
                "wcag_refs": ["1.2.2", "1.2.3", "1.4.13"],
            }
        )
    if context["fallbacks_used"]:
        risks.append(
            {
                "title": "Accessibility acceptance criteria are under-specified",
                "description": "Sparse brief inputs require conservative accessibility validation tasks before autonomous implementation.",
                "severity": "high",
                "owner": "Product owner",
                "affected_user_group_ids": group_ids,
                "wcag_refs": ["2.1.1", "3.3.2", "4.1.2"],
            }
        )
    for text in context["risks"]:
        if _accessibility_relevant(text):
            risks.append(
                {
                    "title": _risk_title(text),
                    "description": text,
                    "severity": "high",
                    "owner": "Design owner",
                    "affected_user_group_ids": group_ids,
                    "wcag_refs": ["1.3.1", "2.1.1", "3.3.2"],
                }
            )
    return [{**risk, "id": f"AR{index}", "source_idea_ids": source_idea_ids} for index, risk in enumerate(risks, 1)]


def _wcag_checks(context: dict[str, Any], risks: list[dict[str, Any]], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    risk_ids = [risk["id"] for risk in risks]
    return [
        {
            **config,
            "validation_method": _validation_method(config["principle"], context),
            "risk_ids": risk_ids,
            "source_idea_ids": source_idea_ids,
        }
        for config in _WCAG_CHECK_CONFIGS
    ]


def _inclusive_design_opportunities(
    context: dict[str, Any],
    user_groups: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    group_ids = [group["id"] for group in user_groups]
    return [
        {
            "id": "IDO1",
            "title": "Accessible task model",
            "owner": "Product owner",
            "opportunity": f"Define the minimal accessible path for {context['primary_user']} to complete {context['primary_scope']}.",
            "expected_benefit": "Keeps accessibility requirements tied to the core value workflow instead of late-stage UI polish.",
            "affected_user_group_ids": group_ids,
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "IDO2",
            "title": "Multi-modal review evidence",
            "owner": "Design owner",
            "opportunity": "Represent status, priority, errors, and generated recommendations with text, structure, and state changes.",
            "expected_benefit": "Improves comprehension for screen reader users and users scanning complex review workflows.",
            "affected_user_group_ids": [group for group in group_ids if group in {"visual", "cognitive"}],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "IDO3",
            "title": "Assistive technology validation loop",
            "owner": "Research owner",
            "opportunity": f"Include keyboard and screen reader checks in the validation plan: {context['validation_plan']}",
            "expected_benefit": "Finds blocking accessibility failures before implementation handoff or pilot launch.",
            "affected_user_group_ids": group_ids,
            "source_idea_ids": source_idea_ids,
        },
    ]


def _validation_tasks(
    context: dict[str, Any],
    risks: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    has_sparse_inputs = bool(context["fallbacks_used"])
    return [
        {
            "id": "AVT1",
            "task": "Keyboard-only primary journey",
            "owner": "Engineering owner",
            "priority": "high",
            "method": f"Complete {context['primary_scope']} using keyboard navigation only.",
            "acceptance_criteria": "No pointer-only controls, focus traps, missing focus indicators, or unreachable workflow steps.",
            "risk_ids": [risk["id"] for risk in risks if "keyboard" in risk["title"].lower()],
            "wcag_check_ids": ["WCAG2"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "AVT2",
            "task": "Screen reader semantic pass",
            "owner": "Design owner",
            "priority": "high",
            "method": "Review headings, labels, roles, names, status messages, and generated content with assistive technology.",
            "acceptance_criteria": "A user can identify page purpose, control names, current state, errors, and completion result without visual-only cues.",
            "risk_ids": [risk["id"] for risk in risks if set(risk["wcag_refs"]) & {"1.3.1", "4.1.2", "4.1.3"}],
            "wcag_check_ids": ["WCAG1", "WCAG4"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "AVT3",
            "task": "Error recovery and cognitive load review",
            "owner": "Product owner",
            "priority": "high" if has_sparse_inputs else "medium",
            "method": "Walk through empty, error, loading, long-content, and recommendation-review states with plain-language criteria.",
            "acceptance_criteria": "Every error has a clear cause, next step, owner, and recovery route; dense decisions are chunked and reversible.",
            "risk_ids": [risk["id"] for risk in risks if "understand" in risk["title"].lower() or "under-specified" in risk["title"].lower()],
            "wcag_check_ids": ["WCAG3"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "AVT4",
            "task": "Accessibility acceptance criteria disposition",
            "owner": "Product owner",
            "priority": "high" if has_sparse_inputs else "medium",
            "method": "Record pass, fail, defer, or not-applicable status for each WCAG-oriented check before implementation starts.",
            "acceptance_criteria": f"All {len(checks)} WCAG-oriented checks have an owner-approved disposition and linked evidence.",
            "risk_ids": [risk["id"] for risk in risks],
            "wcag_check_ids": [check["id"] for check in checks],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field in ("why_this_now", "synthesis_rationale", "validation_plan"):
        text = _first_text(design_brief.get(field))
        if text:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": text,
                    "source_idea_ids": source_idea_ids,
                }
            )
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            refs.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "summary": _first_text(idea.get("one_liner"), idea.get("problem"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "inspiring_insight",
                    "summary": _first_text(idea.get("value_proposition"), idea.get("solution"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
    return refs


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


def _owners() -> list[dict[str, str]]:
    return [
        {"role": "Product owner", "responsibility": "Own inclusive task scope, acceptance criteria, and launch gating."},
        {"role": "Design owner", "responsibility": "Own accessible information architecture, content alternatives, and visual design checks."},
        {"role": "Engineering owner", "responsibility": "Own semantic implementation, keyboard behavior, focus management, and assistive technology support."},
        {"role": "Research owner", "responsibility": "Include users with access needs and assistive technology validation in research plans."},
    ]


def _review_gate(context: dict[str, Any], risks: list[dict[str, Any]]) -> str:
    if context["fallbacks_used"]:
        return "needs_accessibility_discovery"
    if any(risk["severity"] == "high" for risk in risks):
        return "accessibility_review_required"
    return "conditional_handoff_ok"


def _group_relevance(group_id: str, context: dict[str, Any]) -> str:
    if group_id == "visual":
        return f"Applies to reading, reviewing, and acting on {context['product_concept']}."
    if group_id == "motor":
        return f"Applies to completing {context['primary_scope']} in {context['workflow_context']}."
    if group_id == "cognitive":
        return "Applies to understanding generated recommendations, errors, and next-step decisions."
    return "Applies because source text references audio, video, call, voice, or meeting workflows."


def _validation_method(principle: str, context: dict[str, Any]) -> str:
    if principle == "perceivable":
        return "Inspect semantic structure, text alternatives, contrast, and non-color status treatment."
    if principle == "operable":
        return f"Run keyboard-only completion of {context['primary_scope']} and record focus behavior."
    if principle == "understandable":
        return "Review language, errors, instructions, and recovery states with the product owner."
    return "Inspect accessible names, roles, states, and live status announcements in implementation."


def _visual_heavy(context: dict[str, Any]) -> bool:
    terms = ("dashboard", "chart", "visual", "color", "status", "report", "summary", "analytics")
    return any(term in context["source_text"] for term in terms)


def _accessibility_relevant(text: str) -> bool:
    normalized = text.lower()
    terms = (
        "accessibility",
        "screen reader",
        "keyboard",
        "contrast",
        "wcag",
        "focus",
        "visual",
        "cognitive",
        "assistive",
    )
    return any(term in normalized for term in terms)


def _risk_title(text: str) -> str:
    compacted = _compact(text).rstrip(".")
    if len(compacted) <= 72:
        return compacted
    return compacted[:69].rstrip() + "..."


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _first_with_label(
    fallbacks: list[str], field: str, *candidates: tuple[Any, str]
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, dict):
        return [_compact(f"{key}: {item}") for key, item in sorted(value.items()) if _compact(item)]
    if isinstance(value, list | tuple | set):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return [_compact(item) for item in values if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _markdown_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return _compact(value) or default
    if isinstance(value, dict | list):
        if not value:
            return default
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _compact(value) or default


def _markdown_list(value: Any) -> str:
    values = _string_list(value)
    return ", ".join(values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
