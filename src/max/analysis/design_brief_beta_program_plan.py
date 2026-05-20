"""Deterministic beta program plans for persisted design briefs."""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.beta_program_plan"
SCHEMA_VERSION = "max.design_brief.beta_program_plan.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "name",
    "owner",
    "cadence_or_timing",
    "criteria_or_action",
    "evidence_or_metric",
)


def build_design_brief_beta_program_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a beta program plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _context(design_brief, lead_idea)
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_source_risks(source_ideas)]
    )
    evidence_count = _evidence_count(source_ideas)
    beta_cohorts = _beta_cohorts(context, design_brief)
    eligibility = _eligibility_criteria(context, design_brief, evidence_count)
    cadence = _feedback_cadence(context)
    exit_criteria = _exit_criteria(context, design_brief, evidence_count)
    mitigations = _risk_mitigations(context, risks)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at")
            or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "program_goal": (
                f"Validate {context['product_concept']} with controlled early users "
                f"before broader release."
            ),
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "fallbacks_used": context["fallbacks_used"],
            "cohort_count": len(beta_cohorts),
            "eligibility_count": len(eligibility),
            "feedback_touchpoint_count": len(cadence),
            "exit_criteria_count": len(exit_criteria),
            "risk_mitigation_count": len(mitigations),
            "source_evidence_count": evidence_count,
        },
        "beta_cohorts": beta_cohorts,
        "eligibility_criteria": eligibility,
        "feedback_cadence": cadence,
        "exit_criteria": exit_criteria,
        "risk_mitigations": mitigations,
        "source_ideas": source_ideas,
    }


def render_design_brief_beta_program_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render a beta program plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported beta program plan format: {fmt}")
    return _render_markdown(report)


def _render_markdown(report: dict[str, Any]) -> str:
    brief = _dict_value(report.get("design_brief"))
    summary = _dict_value(report.get("summary"))
    lines = [
        f"# Beta Program Plan: {_text(brief.get('title'), 'Untitled design brief')}",
        "",
        f"Schema: `{_text(report.get('schema_version'), 'unknown')}`",
        f"Design brief: `{_text(brief.get('id'), 'unknown')}`",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {_join_text(brief.get('source_idea_ids'), 'design brief')}",
        "",
        "## Program Summary",
        "",
        f"- Goal: {_text(summary.get('program_goal'), 'Not specified')}",
        f"- Target user: {_text(summary.get('target_user'), 'Not specified')}",
        f"- Buyer: {_text(summary.get('buyer'), 'Not specified')}",
        f"- Workflow: {_text(summary.get('workflow_context'), 'Not specified')}",
        f"- Fallbacks used: {_join_text(summary.get('fallbacks_used'), 'none')}",
        "",
        "## Beta Cohorts",
        "",
    ]

    for cohort in _list_of_dicts(report.get("beta_cohorts")):
        lines.extend(
            [
                f"### {_text(cohort.get('id'), 'cohort')}: {_text(cohort.get('name'), 'Unnamed cohort')}",
                "",
                f"- Participants: {_text(cohort.get('participants'), 'Not specified')}",
                f"- Size: {_text(cohort.get('size'), 'Not specified')}",
                f"- Owner: {_text(cohort.get('owner'), 'Unassigned')}",
                f"- Purpose: {_text(cohort.get('purpose'), 'Not specified')}",
                f"- Entry signal: {_text(cohort.get('entry_signal'), 'Not specified')}",
                "",
            ]
        )
    if not _list_of_dicts(report.get("beta_cohorts")):
        lines.extend(["- None", ""])

    lines.extend(["## Eligibility Criteria", ""])
    for item in _list_of_dicts(report.get("eligibility_criteria")):
        lines.append(
            f"- **{_text(item.get('id'), 'criterion')}**: {_text(item.get('criterion'), 'Not specified')} "
            f"Evidence: {_text(item.get('evidence'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("eligibility_criteria")):
        lines.append("- None")

    lines.extend(["", "## Feedback Cadence", ""])
    for item in _list_of_dicts(report.get("feedback_cadence")):
        lines.append(
            f"- **{_text(item.get('cadence'), 'unscheduled')}** ({_text(item.get('owner'), 'Unassigned')}): "
            f"{_text(item.get('activity'), 'Not specified')} Output: {_text(item.get('output'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("feedback_cadence")):
        lines.append("- None")

    lines.extend(["", "## Exit Criteria", ""])
    for item in _list_of_dicts(report.get("exit_criteria")):
        lines.append(
            f"- **{_text(item.get('decision'), 'decision')}**: {_text(item.get('criterion'), 'Not specified')} "
            f"Metric: {_text(item.get('metric'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("exit_criteria")):
        lines.append("- None")

    lines.extend(["", "## Risk Mitigations", ""])
    for item in _list_of_dicts(report.get("risk_mitigations")):
        lines.append(
            f"- **{_text(item.get('risk'), 'Risk')}** ({_text(item.get('owner'), 'Unassigned')}): "
            f"{_text(item.get('mitigation'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("risk_mitigations")):
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    brief = _dict_value(report.get("design_brief"))
    common = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
    }
    rows: list[dict[str, str]] = []
    for cohort in _list_of_dicts(report.get("beta_cohorts")):
        rows.append(
            _csv_row(
                **common,
                section="beta_cohorts",
                item_id=cohort.get("id"),
                name=cohort.get("name"),
                owner=cohort.get("owner"),
                cadence_or_timing=cohort.get("sequence"),
                criteria_or_action=cohort.get("purpose"),
                evidence_or_metric=cohort.get("entry_signal"),
            )
        )
    for item in _list_of_dicts(report.get("eligibility_criteria")):
        rows.append(
            _csv_row(
                **common,
                section="eligibility_criteria",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                criteria_or_action=item.get("criterion"),
                evidence_or_metric=item.get("evidence"),
            )
        )
    for item in _list_of_dicts(report.get("feedback_cadence")):
        rows.append(
            _csv_row(
                **common,
                section="feedback_cadence",
                item_id=item.get("id"),
                name=item.get("activity"),
                owner=item.get("owner"),
                cadence_or_timing=item.get("cadence"),
                criteria_or_action=item.get("prompt"),
                evidence_or_metric=item.get("output"),
            )
        )
    for item in _list_of_dicts(report.get("exit_criteria")):
        rows.append(
            _csv_row(
                **common,
                section="exit_criteria",
                item_id=item.get("id"),
                name=item.get("decision"),
                owner=item.get("owner"),
                criteria_or_action=item.get("criterion"),
                evidence_or_metric=item.get("metric"),
            )
        )
    for item in _list_of_dicts(report.get("risk_mitigations")):
        rows.append(
            _csv_row(
                **common,
                section="risk_mitigations",
                item_id=item.get("id"),
                name=item.get("risk"),
                owner=item.get("owner"),
                criteria_or_action=item.get("mitigation"),
                evidence_or_metric=item.get("trigger"),
            )
        )
    return rows


def _csv_row(**values: Any) -> dict[str, str]:
    return {column: _text(values.get(column), "") for column in CSV_COLUMNS}


def _context(
    design_brief: dict[str, Any], lead_idea: dict[str, Any] | None
) -> dict[str, Any]:
    title = _text(design_brief.get("title"), "design brief")
    fallback_base = _fallback_name(title)
    fallbacks_used: list[str] = []

    target_user = _first_text(
        design_brief.get("specific_user"),
        lead_idea and lead_idea.get("specific_user"),
    )
    if not target_user:
        target_user = f"{fallback_base} users"
        fallbacks_used.append("specific_user")

    buyer = _first_text(design_brief.get("buyer"), lead_idea and lead_idea.get("buyer"))
    if not buyer:
        buyer = f"{fallback_base} sponsor"
        fallbacks_used.append("buyer")

    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
    )
    if not workflow:
        workflow = f"{fallback_base} validation workflow"
        fallbacks_used.append("workflow_context")

    product_concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        title,
    )

    return {
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": product_concept,
        "fallbacks_used": fallbacks_used,
    }


def _beta_cohorts(
    context: dict[str, Any], design_brief: dict[str, Any]
) -> list[dict[str, str]]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    early_size = "3-5 participants" if readiness >= 75 else "2-3 participants"
    return [
        {
            "id": "cohort-1",
            "sequence": "week 1",
            "name": "Design Partner Beta",
            "participants": context["target_user"],
            "size": early_size,
            "owner": "Product lead",
            "purpose": f"Confirm {context['workflow_context']} reaches first value with close observation.",
            "entry_signal": "Participant owns the workflow and agrees to two structured feedback sessions.",
        },
        {
            "id": "cohort-2",
            "sequence": "weeks 2-3",
            "name": "Controlled Expansion Beta",
            "participants": f"{context['target_user']} plus adjacent operators",
            "size": "5-8 participants",
            "owner": "Customer owner",
            "purpose": "Test repeatability, support load, and sponsor-visible value across more teams.",
            "entry_signal": "Cohort 1 completes core workflow without a stop-condition breach.",
        },
        {
            "id": "cohort-3",
            "sequence": "week 4",
            "name": "Release Candidate Beta",
            "participants": f"{context['buyer']} nominated accounts",
            "size": "8-12 participants",
            "owner": "GTM owner",
            "purpose": "Validate launch readiness, references, and expansion objections before general availability.",
            "entry_signal": "Exit review approves instrumentation, support playbook, and risk mitigations.",
        },
    ]


def _eligibility_criteria(
    context: dict[str, Any], design_brief: dict[str, Any], evidence_count: int
) -> list[dict[str, str]]:
    scope = _string_list(design_brief.get("mvp_scope"))
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        "Structured beta feedback and usage review are accepted as the validation method.",
    )
    return [
        {
            "id": "EL1",
            "name": "Workflow ownership",
            "owner": "Product lead",
            "criterion": f"Participant actively performs {context['workflow_context']}.",
            "evidence": "Recruiting note names role, workflow trigger, and expected outcome.",
        },
        {
            "id": "EL2",
            "name": "Scoped use case",
            "owner": "Engineering lead",
            "criterion": (
                f"Beta use is limited to {', '.join(scope)}."
                if scope
                else "Beta use is limited to the smallest testable product behavior."
            ),
            "evidence": "MVP scope is acknowledged before enablement.",
        },
        {
            "id": "EL3",
            "name": "Feedback commitment",
            "owner": "Research lead",
            "criterion": f"Participant accepts the feedback plan: {validation_plan}",
            "evidence": "Calendar holds or written feedback commitment.",
        },
        {
            "id": "EL4",
            "name": "Source evidence traceability",
            "owner": "Product lead",
            "criterion": f"Beta learning can be compared with {evidence_count} linked source evidence item(s).",
            "evidence": "Feedback notes reference source idea, assumption, or brief field.",
        },
    ]


def _feedback_cadence(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "FC1",
            "cadence": "Kickoff",
            "owner": "Product lead",
            "activity": "Confirm beta goal, workflow, data boundaries, and success definition.",
            "prompt": f"What must be true for {context['workflow_context']} to be worth repeating?",
            "output": "Signed beta brief and baseline workflow notes.",
        },
        {
            "id": "FC2",
            "cadence": "Twice weekly",
            "owner": "Research lead",
            "activity": "Collect structured feedback from active participants.",
            "prompt": "What blocked first value, what worked, and what would make this indispensable?",
            "output": "Tagged feedback notes with severity and participant segment.",
        },
        {
            "id": "FC3",
            "cadence": "Weekly",
            "owner": "Engineering lead",
            "activity": "Review usage, defects, support load, and instrumentation coverage.",
            "prompt": "Which beta issues require product changes before the next cohort?",
            "output": "Beta health summary and fix-forward queue.",
        },
        {
            "id": "FC4",
            "cadence": "Phase exit",
            "owner": "Product lead",
            "activity": "Decide expand, revise, or stop for the next cohort.",
            "prompt": "Does evidence justify expanding exposure or changing the brief?",
            "output": "Decision record with owner, rationale, and next cohort scope.",
        },
    ]


def _exit_criteria(
    context: dict[str, Any], design_brief: dict[str, Any], evidence_count: int
) -> list[dict[str, str]]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    return [
        {
            "id": "EX1",
            "decision": "Expand",
            "owner": "Product lead",
            "criterion": f"At least 70% of active beta participants complete {context['workflow_context']} without concierge rescue.",
            "metric": "Workflow completion rate >= 70%.",
        },
        {
            "id": "EX2",
            "decision": "Revise",
            "owner": "Engineering lead",
            "criterion": "Top beta blockers are reproducible, bounded, and assigned to a fix-forward owner.",
            "metric": "Every severity 1 or 2 blocker has owner, date, and validation step.",
        },
        {
            "id": "EX3",
            "decision": "Launch readiness",
            "owner": "GTM owner",
            "criterion": f"{context['buyer']} can explain value, qualification, and support path for the next cohort.",
            "metric": "Sponsor readiness review passes with no launch-blocking objection.",
        },
        {
            "id": "EX4",
            "decision": "Evidence update",
            "owner": "Research lead",
            "criterion": f"Beta adds at least 3 new evidence records beyond {evidence_count} source evidence item(s).",
            "metric": f"Readiness score starts at {readiness:.1f} and has a documented beta disposition.",
        },
    ]


def _risk_mitigations(
    context: dict[str, Any], risks: list[str]
) -> list[dict[str, str]]:
    risk_items = risks[:3] or [
        "Beta feedback is too thin to justify expansion.",
        "Participants use the beta outside the intended workflow.",
    ]
    mitigations = [
        {
            "id": f"RM{index}",
            "risk": risk,
            "owner": "Risk owner" if index == 1 else "Product lead",
            "trigger": "Risk appears in two participant sessions or blocks a phase exit.",
            "mitigation": f"Pause expansion for {context['target_user']} until owner records disposition, fix, or explicit acceptance.",
        }
        for index, risk in enumerate(risk_items, start=1)
    ]
    mitigations.append(
        {
            "id": f"RM{len(mitigations) + 1}",
            "risk": "Support or onboarding load exceeds beta capacity.",
            "owner": "Support owner",
            "trigger": "More than two unresolved support issues remain open at weekly review.",
            "mitigation": "Reduce cohort size, add enablement, and defer the next cohort until support paths are documented.",
        }
    )
    return mitigations


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
                sources.append({"idea_id": idea_id, "role": "supporting", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append(
                {
                    "id": idea_id,
                    "role": source.get("role", "source"),
                    "rank": source.get("rank", 0),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _evidence_count(source_ideas: list[dict[str, Any]]) -> int:
    return sum(
        len(_string_list(idea.get("evidence_signals")))
        + len(_string_list(idea.get("inspiring_insights")))
        for idea in source_ideas
        if not idea.get("missing")
    )


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _text(value: Any, fallback: str) -> str:
    text = "" if value is None else str(value).strip()
    return text or fallback


def _join_text(value: Any, fallback: str) -> str:
    items = _string_list(value)
    return ", ".join(items) if items else fallback


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(str(value).strip())
    return deduped


def _fallback_name(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    return " ".join(words[:4]) if words else "design brief"
