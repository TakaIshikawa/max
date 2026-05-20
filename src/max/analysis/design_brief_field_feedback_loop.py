"""Deterministic field feedback loop plans for persisted design briefs."""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.field_feedback_loop"
SCHEMA_VERSION = "max.design_brief.field_feedback_loop.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "name",
    "owner",
    "cadence_or_priority",
    "rule_or_prompt",
    "output_or_threshold",
)


def build_design_brief_field_feedback_loop(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a field feedback loop plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _context(design_brief, lead_idea)
    evidence = _evidence_references(design_brief, source_ideas)
    sources = _feedback_sources(context, evidence)
    prompts = _collection_prompts(context, evidence)
    triage = _triage_rules(context)
    routing = _routing_owners(context)
    cadence = _synthesis_cadence(context)
    thresholds = _decision_thresholds(context, design_brief)

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
            "loop_goal": (
                f"Convert field feedback about {context['product_concept']} into "
                "traceable decisions about the idea and spec."
            ),
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "fallbacks_used": context["fallbacks_used"],
            "feedback_source_count": len(sources),
            "collection_prompt_count": len(prompts),
            "triage_rule_count": len(triage),
            "routing_owner_count": len(routing),
            "decision_threshold_count": len(thresholds),
            "evidence_reference_count": len(evidence),
        },
        "feedback_sources": sources,
        "collection_prompts": prompts,
        "triage_rules": triage,
        "routing_owners": routing,
        "synthesis_cadence": cadence,
        "decision_thresholds": thresholds,
        "evidence_references": evidence,
        "source_ideas": source_ideas,
    }


def render_design_brief_field_feedback_loop(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render a field feedback loop as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported field feedback loop format: {fmt}")
    return _render_markdown(report)


def _render_markdown(report: dict[str, Any]) -> str:
    brief = _dict_value(report.get("design_brief"))
    summary = _dict_value(report.get("summary"))
    lines = [
        f"# Field Feedback Loop: {_text(brief.get('title'), 'Untitled design brief')}",
        "",
        f"Schema: `{_text(report.get('schema_version'), 'unknown')}`",
        f"Design brief: `{_text(brief.get('id'), 'unknown')}`",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {_join_text(brief.get('source_idea_ids'), 'design brief')}",
        "",
        "## Loop Summary",
        "",
        f"- Goal: {_text(summary.get('loop_goal'), 'Not specified')}",
        f"- Target user: {_text(summary.get('target_user'), 'Not specified')}",
        f"- Buyer: {_text(summary.get('buyer'), 'Not specified')}",
        f"- Workflow: {_text(summary.get('workflow_context'), 'Not specified')}",
        f"- Fallbacks used: {_join_text(summary.get('fallbacks_used'), 'none')}",
        "",
        "## Feedback Sources",
        "",
    ]

    for source in _list_of_dicts(report.get("feedback_sources")):
        lines.append(
            f"- **{_text(source.get('name'), 'Source')}** ({_text(source.get('owner'), 'Unassigned')}): "
            f"{_text(source.get('capture_method'), 'Not specified')} Cadence: {_text(source.get('cadence'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("feedback_sources")):
        lines.append("- None")

    lines.extend(["", "## Collection Prompts", ""])
    for prompt in _list_of_dicts(report.get("collection_prompts")):
        lines.append(
            f"- **{_text(prompt.get('id'), 'prompt')}**: {_text(prompt.get('prompt'), 'Not specified')} "
            f"Maps to: {_text(prompt.get('maps_to'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("collection_prompts")):
        lines.append("- None")

    lines.extend(["", "## Triage Rules", ""])
    for rule in _list_of_dicts(report.get("triage_rules")):
        lines.append(
            f"- **{_text(rule.get('priority'), 'priority')}**: {_text(rule.get('rule'), 'Not specified')} "
            f"Action: {_text(rule.get('action'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("triage_rules")):
        lines.append("- None")

    lines.extend(["", "## Routing Owners", ""])
    for owner in _list_of_dicts(report.get("routing_owners")):
        lines.append(
            f"- **{_text(owner.get('owner'), 'Owner')}**: {_text(owner.get('feedback_type'), 'Not specified')} "
            f"Output: {_text(owner.get('output'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("routing_owners")):
        lines.append("- None")

    lines.extend(["", "## Synthesis Cadence", ""])
    for item in _list_of_dicts(report.get("synthesis_cadence")):
        lines.append(
            f"- **{_text(item.get('cadence'), 'cadence')}** ({_text(item.get('owner'), 'Unassigned')}): "
            f"{_text(item.get('activity'), 'Not specified')} Output: {_text(item.get('output'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("synthesis_cadence")):
        lines.append("- None")

    lines.extend(["", "## Decision Thresholds", ""])
    for threshold in _list_of_dicts(report.get("decision_thresholds")):
        lines.append(
            f"- **{_text(threshold.get('decision'), 'decision')}**: {_text(threshold.get('threshold'), 'Not specified')} "
            f"Spec impact: {_text(threshold.get('spec_impact'), 'Not specified')}"
        )
    if not _list_of_dicts(report.get("decision_thresholds")):
        lines.append("- None")

    lines.extend(["", "## Evidence References", ""])
    evidence = _list_of_dicts(report.get("evidence_references"))
    if evidence:
        for item in evidence:
            lines.append(
                f"- **{_text(item.get('id'), 'evidence')}** ({_text(item.get('source_idea_id'), 'source')}): "
                f"{_text(item.get('text'), 'Not specified')}"
            )
    else:
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
    for item in _list_of_dicts(report.get("feedback_sources")):
        rows.append(
            _csv_row(
                **common,
                section="feedback_sources",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                cadence_or_priority=item.get("cadence"),
                rule_or_prompt=item.get("capture_method"),
                output_or_threshold=item.get("output"),
            )
        )
    for item in _list_of_dicts(report.get("collection_prompts")):
        rows.append(
            _csv_row(
                **common,
                section="collection_prompts",
                item_id=item.get("id"),
                name=item.get("maps_to"),
                owner=item.get("owner"),
                rule_or_prompt=item.get("prompt"),
                output_or_threshold=item.get("expected_signal"),
            )
        )
    for item in _list_of_dicts(report.get("triage_rules")):
        rows.append(
            _csv_row(
                **common,
                section="triage_rules",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                cadence_or_priority=item.get("priority"),
                rule_or_prompt=item.get("rule"),
                output_or_threshold=item.get("action"),
            )
        )
    for item in _list_of_dicts(report.get("routing_owners")):
        rows.append(
            _csv_row(
                **common,
                section="routing_owners",
                item_id=item.get("id"),
                name=item.get("feedback_type"),
                owner=item.get("owner"),
                cadence_or_priority=item.get("sla"),
                rule_or_prompt=item.get("route_when"),
                output_or_threshold=item.get("output"),
            )
        )
    for item in _list_of_dicts(report.get("synthesis_cadence")):
        rows.append(
            _csv_row(
                **common,
                section="synthesis_cadence",
                item_id=item.get("id"),
                name=item.get("activity"),
                owner=item.get("owner"),
                cadence_or_priority=item.get("cadence"),
                rule_or_prompt=item.get("inputs"),
                output_or_threshold=item.get("output"),
            )
        )
    for item in _list_of_dicts(report.get("decision_thresholds")):
        rows.append(
            _csv_row(
                **common,
                section="decision_thresholds",
                item_id=item.get("id"),
                name=item.get("decision"),
                owner=item.get("owner"),
                cadence_or_priority=item.get("review_window"),
                rule_or_prompt=item.get("threshold"),
                output_or_threshold=item.get("spec_impact"),
            )
        )
    for item in _list_of_dicts(report.get("evidence_references")):
        rows.append(
            _csv_row(
                **common,
                section="evidence_references",
                item_id=item.get("id"),
                name=item.get("source_idea_id"),
                owner=item.get("kind"),
                rule_or_prompt=item.get("text"),
                output_or_threshold=item.get("source_title"),
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

    target_user = _first_text(design_brief.get("specific_user"), lead_idea and lead_idea.get("specific_user"))
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
        workflow = f"{fallback_base} field workflow"
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


def _feedback_sources(
    context: dict[str, Any], evidence: list[dict[str, str]]
) -> list[dict[str, str]]:
    return [
        {
            "id": "FS1",
            "name": "Customer calls",
            "owner": "Research lead",
            "cadence": "weekly",
            "capture_method": f"Interview {context['target_user']} about workflow fit, friction, and repeat intent.",
            "output": "Tagged interview notes linked to assumptions.",
        },
        {
            "id": "FS2",
            "name": "Sales and success notes",
            "owner": "Customer owner",
            "cadence": "twice weekly",
            "capture_method": f"Collect objections and sponsor signals from {context['buyer']} conversations.",
            "output": "Field note digest with account, segment, and urgency.",
        },
        {
            "id": "FS3",
            "name": "Support and defect queue",
            "owner": "Support owner",
            "cadence": "daily",
            "capture_method": "Tag tickets, defects, and workarounds that block first value.",
            "output": "Severity-ranked queue routed to product or engineering.",
        },
        {
            "id": "FS4",
            "name": "Source evidence comparison",
            "owner": "Product lead",
            "cadence": "phase exit",
            "capture_method": f"Compare field feedback against {len(evidence)} persisted source evidence item(s).",
            "output": "Evidence delta and assumption disposition.",
        },
    ]


def _collection_prompts(
    context: dict[str, Any], evidence: list[dict[str, str]]
) -> list[dict[str, str]]:
    source_hint = evidence[0]["text"] if evidence else "the original source assumption"
    return [
        {
            "id": "CP1",
            "owner": "Research lead",
            "maps_to": "workflow_value",
            "prompt": f"Where did {context['workflow_context']} create or fail to create measurable value?",
            "expected_signal": "Specific before/after workflow detail.",
        },
        {
            "id": "CP2",
            "owner": "Customer owner",
            "maps_to": "buyer_pull",
            "prompt": f"What would make {context['buyer']} expand, defer, or reject this idea?",
            "expected_signal": "Budget, urgency, approval, or risk language.",
        },
        {
            "id": "CP3",
            "owner": "Product lead",
            "maps_to": "source_evidence",
            "prompt": f"Does new feedback confirm, contradict, or refine this source signal: {source_hint}",
            "expected_signal": "Confirmed, contradicted, or changed assumption tag.",
        },
        {
            "id": "CP4",
            "owner": "Engineering lead",
            "maps_to": "spec_change",
            "prompt": "Which requested change alters scope, data handling, integration, or acceptance criteria?",
            "expected_signal": "Proposed spec change with impact and owner.",
        },
    ]


def _triage_rules(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "TR1",
            "name": "Blocker",
            "priority": "P0",
            "owner": "Product lead",
            "rule": f"Feedback shows {context['target_user']} cannot complete the core workflow.",
            "action": "Route to product and engineering within one business day.",
        },
        {
            "id": "TR2",
            "name": "Spec change",
            "priority": "P1",
            "owner": "Engineering lead",
            "rule": "Feedback changes scope, acceptance criteria, integration behavior, or data assumptions.",
            "action": "Create a spec delta with decision owner and validation step.",
        },
        {
            "id": "TR3",
            "name": "Commercial signal",
            "priority": "P1",
            "owner": "GTM owner",
            "rule": "Buyer feedback changes willingness to pay, urgency, procurement path, or segment fit.",
            "action": "Route to GTM and product for packaging or positioning review.",
        },
        {
            "id": "TR4",
            "name": "Evidence update",
            "priority": "P2",
            "owner": "Research lead",
            "rule": "Feedback confirms or contradicts source evidence without blocking the current workflow.",
            "action": "Attach to evidence log and include in weekly synthesis.",
        },
    ]


def _routing_owners(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "RO1",
            "feedback_type": "Workflow fit and user pain",
            "owner": "Product lead",
            "sla": "2 business days",
            "route_when": f"Feedback concerns {context['workflow_context']} value, sequence, or scope.",
            "output": "Idea disposition or backlog change.",
        },
        {
            "id": "RO2",
            "feedback_type": "Implementation and reliability",
            "owner": "Engineering lead",
            "sla": "1 business day for P0, 3 business days otherwise",
            "route_when": "Feedback identifies defects, integration gaps, latency, or data handling issues.",
            "output": "Spec delta, defect, or technical risk update.",
        },
        {
            "id": "RO3",
            "feedback_type": "Commercial and adoption signal",
            "owner": "GTM owner",
            "sla": "3 business days",
            "route_when": f"Feedback comes from {context['buyer']} or affects segment qualification.",
            "output": "Positioning, pricing, or launch-readiness note.",
        },
        {
            "id": "RO4",
            "feedback_type": "Support and enablement",
            "owner": "Support owner",
            "sla": "2 business days",
            "route_when": "Feedback shows confusion, missing documentation, or repeated support needs.",
            "output": "Enablement update or support playbook change.",
        },
    ]


def _synthesis_cadence(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "SC1",
            "cadence": "Daily during active field exposure",
            "owner": "Product lead",
            "activity": "Review P0/P1 feedback and unblock routing decisions.",
            "inputs": "New field notes, defects, support tickets, and sales objections.",
            "output": "Daily triage log with owner and next action.",
        },
        {
            "id": "SC2",
            "cadence": "Weekly",
            "owner": "Research lead",
            "activity": f"Synthesize patterns for {context['target_user']} and buyer feedback.",
            "inputs": "Tagged feedback, source evidence, usage notes, and decision log.",
            "output": "Evidence summary with confirmed, contradicted, and changed assumptions.",
        },
        {
            "id": "SC3",
            "cadence": "Before spec freeze or cohort expansion",
            "owner": "Product lead",
            "activity": "Decide whether feedback changes the idea, spec, or launch path.",
            "inputs": "Weekly synthesis, unresolved blockers, and threshold status.",
            "output": "Change, continue, or stop decision memo.",
        },
    ]


def _decision_thresholds(
    context: dict[str, Any], design_brief: dict[str, Any]
) -> list[dict[str, str]]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    return [
        {
            "id": "DT1",
            "decision": "Change the idea",
            "owner": "Product lead",
            "review_window": "weekly",
            "threshold": "3+ qualified accounts reject the core value proposition for the same reason.",
            "spec_impact": "Revise problem framing, target segment, or product concept before more build work.",
        },
        {
            "id": "DT2",
            "decision": "Change the spec",
            "owner": "Engineering lead",
            "review_window": "before implementation milestone",
            "threshold": f"2+ {context['target_user']} sessions require a new workflow step, integration, or acceptance criterion.",
            "spec_impact": "Open a spec delta and hold launch scope until accepted or rejected.",
        },
        {
            "id": "DT3",
            "decision": "Continue unchanged",
            "owner": "Research lead",
            "review_window": "phase exit",
            "threshold": "70%+ of high-confidence feedback confirms the workflow value and no P0 blocker remains open.",
            "spec_impact": f"Keep current spec and record readiness baseline of {readiness:.1f}.",
        },
        {
            "id": "DT4",
            "decision": "Stop or pause",
            "owner": "Executive sponsor",
            "review_window": "any time",
            "threshold": "A privacy, trust, reliability, or buyer-path blocker cannot be mitigated inside the current scope.",
            "spec_impact": "Pause field exposure and require an explicit restart decision.",
        },
    ]


def _evidence_references(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        source_id = _text(idea.get("id"), "source")
        source_title = _text(idea.get("title"), source_id)
        for kind, values in (
            ("evidence_signal", _string_list(idea.get("evidence_signals"))),
            ("inspiring_insight", _string_list(idea.get("inspiring_insights"))),
        ):
            for value in values:
                references.append(
                    {
                        "id": f"ER{len(references) + 1}",
                        "source_idea_id": source_id,
                        "source_title": source_title,
                        "kind": kind,
                        "text": value,
                    }
                )
    if not references:
        references.append(
            {
                "id": "ER1",
                "source_idea_id": _text(design_brief.get("lead_idea_id"), "design_brief"),
                "source_title": _text(design_brief.get("title"), "Design brief"),
                "kind": "fallback",
                "text": "No persisted source evidence was available; collect first field evidence before changing launch scope.",
            }
        )
    return references


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


def _fallback_name(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    return " ".join(words[:4]) if words else "design brief"
