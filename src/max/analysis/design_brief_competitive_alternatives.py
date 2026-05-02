"""Competitive alternatives matrices for design briefs and buildable units."""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.competitive_alternatives_matrix.v1"
KIND = "max.design_brief.competitive_alternatives_matrix"
CSV_COLUMNS: tuple[str, ...] = (
    "competitor_alternative_name",
    "target_segment",
    "differentiators",
    "weaknesses",
    "switching_triggers",
    "evidence_references",
    "recommended_positioning",
)


def build_design_brief_competitive_alternatives(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a competitor-aware alternatives matrix from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    prior_art = _prior_art_records(store, [idea["id"] for idea in source_ideas])
    context = _context_from_brief(design_brief, source_ideas)
    return _build_report(
        entity=design_brief,
        entity_type="design_brief",
        context=context,
        source_ideas=source_ideas,
        prior_art=prior_art,
    )


def build_buildable_unit_competitive_alternatives(
    store: Store,
    unit_id: str,
) -> dict[str, Any] | None:
    """Build a competitive alternatives matrix from a persisted buildable unit."""
    unit = store.get_buildable_unit(unit_id)
    if not unit:
        return None

    source_idea = unit.model_dump(mode="json")
    source_idea["role"] = "lead"
    source_idea["rank"] = 0
    prior_art = _prior_art_records(store, [unit.id])
    context = _context_from_unit(source_idea)
    entity = {
        "id": unit.id,
        "title": unit.title,
        "domain": unit.domain,
        "theme": "",
        "readiness_score": unit.quality_score,
        "design_status": unit.status,
        "lead_idea_id": unit.id,
        "source_idea_ids": [unit.id],
        "created_at": source_idea.get("created_at"),
        "updated_at": source_idea.get("updated_at"),
    }
    return _build_report(
        entity=entity,
        entity_type="buildable_unit",
        context=context,
        source_ideas=[source_idea],
        prior_art=prior_art,
    )


def render_design_brief_competitive_alternatives(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a competitive alternatives matrix as Markdown, CSV, or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_competitive_alternatives_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported competitive alternatives format: {fmt}")

    return render_design_brief_competitive_alternatives_markdown(report)


def render_design_brief_competitive_alternatives_csv(report: dict[str, Any]) -> str:
    """Render a competitive alternatives matrix as deterministic CSV."""
    return _render_csv(report)


def render_design_brief_competitive_alternatives_markdown(report: dict[str, Any]) -> str:
    """Render a competitive alternatives matrix as a concise Markdown review artifact."""
    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Competitive Alternatives Matrix: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Entity: `{report['source']['entity_type']}` `{brief['id']}`",
        f"Status: `{summary['status']}`",
        f"Direct competitors: {summary['direct_competitor_count']}",
        f"Indirect alternatives: {summary['indirect_alternative_count']}",
        f"Evidence gaps: {summary['evidence_gap_count']}",
        "",
        "## Alternatives",
        "",
    ]

    alternatives = _markdown_alternatives(report)
    if alternatives:
        for alternative in alternatives:
            lines.extend(
                [
                    f"### {alternative['id']}: {alternative['name']}",
                    "",
                    f"- Type: {alternative['type']}",
                    f"- Substitution risk: {alternative['substitution_risk']}",
                    f"- Why it matters: {alternative['why_it_matters']}",
                    f"- Positioning response: {alternative['positioning_response']}",
                    f"- Switching cost: {alternative['switching_cost']}",
                    f"- Evidence: {_inline_ids(alternative['source_reference_ids'])}",
                    "",
                ]
            )
    else:
        lines.extend(["- No competitive alternatives are available.", ""])

    lines.extend(["## Positioning Gaps", ""])
    if report.get("evidence_gap_entries"):
        for gap in report["evidence_gap_entries"]:
            lines.append(f"- **{gap['gap']}**: {gap['resolution']} ({gap['owner']})")
    else:
        lines.append("- No positioning gaps are available.")

    lines.extend(["", "## Switching Costs", ""])
    if report.get("switching_friction_entries"):
        for friction in report["switching_friction_entries"]:
            lines.append(
                f"- **{friction['factor']}** ({friction['level']}): {friction['description']}"
            )
    else:
        lines.append("- No switching cost factors are available.")

    lines.extend(["", "## Differentiators", ""])
    if report.get("differentiator_entries"):
        for differentiator in report["differentiator_entries"]:
            lines.extend(
                [
                    f"- **{differentiator['claim']}**: {differentiator['rationale']}",
                    f"  Proof needed: {differentiator['proof_needed']}",
                    f"  Against: {_inline_ids(differentiator['against'])}",
                    f"  Evidence: {_inline_ids(differentiator['source_reference_ids'])}",
                ]
            )
    else:
        lines.append("- No differentiators are available.")

    lines.extend(["", "## Evidence", ""])
    prior_art = report.get("signals", {}).get("prior_art", [])
    if prior_art:
        for record in prior_art:
            evidence_line = (
                f"- `{record['id']}` [{record['source']}] {record['title']} "
                f"(score {float(record['relevance_score']):.3f})"
            )
            if record.get("url"):
                evidence_line += f" - {record['url']}"
            lines.append(evidence_line)
    else:
        lines.append("- No stored prior-art evidence is linked to this report.")

    if report.get("design_brief", {}).get("source_idea_ids"):
        lines.extend(
            [
                "",
                f"Source ideas: {_inline_ids(report['design_brief']['source_idea_ids'])}",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _markdown_alternatives(report: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives: list[dict[str, Any]] = []
    for competitor in report.get("direct_competitors", []):
        alternatives.append(
            {
                "id": competitor.get("id") or f"A{len(alternatives) + 1}",
                "name": competitor.get("name") or "Unnamed direct competitor",
                "type": "Direct competitor",
                "substitution_risk": competitor.get("substitution_risk") or "unknown",
                "why_it_matters": competitor.get("overlap_summary") or "No overlap summary available.",
                "positioning_response": competitor.get("differentiation_response")
                or "No positioning response available.",
                "switching_cost": competitor.get("switching_friction")
                or "No switching cost factor available.",
                "source_reference_ids": _string_list(competitor.get("source_reference_ids")),
            }
        )
    for alternative in report.get("indirect_alternatives", []):
        alternatives.append(
            {
                "id": alternative.get("id") or f"A{len(alternatives) + 1}",
                "name": alternative.get("name") or "Unnamed indirect alternative",
                "type": "Indirect alternative",
                "substitution_risk": alternative.get("substitution_risk") or "unknown",
                "why_it_matters": alternative.get("why_users_choose_it")
                or alternative.get("behavior")
                or "No usage rationale available.",
                "positioning_response": alternative.get("differentiation_response")
                or "No positioning response available.",
                "switching_cost": alternative.get("switching_friction")
                or "No switching cost factor available.",
                "source_reference_ids": _string_list(alternative.get("source_reference_ids")),
            }
        )
    for workaround in report.get("workaround_entries", []):
        alternatives.append(
            {
                "id": workaround.get("id") or f"A{len(alternatives) + 1}",
                "name": workaround.get("behavior") or "Unnamed current workaround",
                "type": "Current workaround",
                "substitution_risk": "medium",
                "why_it_matters": workaround.get("user_job") or "No workaround job available.",
                "positioning_response": _workaround_positioning_response(report),
                "switching_cost": workaround.get("switching_friction")
                or "No switching cost factor available.",
                "source_reference_ids": _string_list(workaround.get("source_reference_ids")),
            }
        )
    return alternatives


def _workaround_positioning_response(report: dict[str, Any]) -> str:
    differentiators = report.get("differentiator_entries", [])
    if differentiators:
        return str(differentiators[0].get("claim") or "No positioning response available.")
    return "No positioning response available."


def competitive_alternatives_filename(
    design_brief: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"competitive-alternatives.{extension}"
    )


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in report.get("matrix_rows", []):
        writer.writerow(_csv_row(report, row))
    return output.getvalue()


def _csv_row(report: dict[str, Any], row: dict[str, Any]) -> dict[str, str]:
    target_segment = str(report.get("summary", {}).get("target_user") or "")
    alternative = str(row.get("alternative") or "")
    substitution_risk = str(row.get("substitution_risk") or "")
    switching_friction = str(row.get("switching_friction") or "")
    differentiators = str(row.get("differentiation_response") or "")
    return {
        "competitor_alternative_name": alternative,
        "target_segment": target_segment,
        "differentiators": differentiators,
        "weaknesses": _csv_sentence(
            "Substitution risk",
            substitution_risk,
            "Switching friction",
            switching_friction,
        ),
        "switching_triggers": _switching_triggers(report),
        "evidence_references": str(row.get("evidence") or ""),
        "recommended_positioning": _recommended_positioning(
            target_segment,
            alternative,
            differentiators,
        ),
    }


def _csv_sentence(first_label: str, first_value: str, second_label: str, second_value: str) -> str:
    parts = []
    if first_value:
        parts.append(f"{first_label}: {first_value}")
    if second_value:
        parts.append(f"{second_label}: {second_value}")
    return "; ".join(parts)


def _switching_triggers(report: dict[str, Any]) -> str:
    context = report.get("competitive_context", {})
    triggers = [
        context.get("value_proposition"),
        context.get("current_workaround"),
        *[
            entry.get("description")
            for entry in report.get("switching_friction_entries", [])
        ],
    ]
    return "; ".join(_string_list(triggers))


def _recommended_positioning(target_segment: str, alternative: str, differentiators: str) -> str:
    if target_segment and alternative and differentiators:
        return f"Position for {target_segment} against {alternative}: {differentiators}"
    if alternative and differentiators:
        return f"Position against {alternative}: {differentiators}"
    return differentiators


def _build_report(
    *,
    entity: dict[str, Any],
    entity_type: str,
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    prior_art: list[dict[str, Any]],
) -> dict[str, Any]:
    direct = _direct_competitors(prior_art, context)
    indirect = _indirect_alternatives(context, source_ideas)
    workarounds = _workaround_entries(context, source_ideas)
    friction = _switching_friction_entries(context)
    differentiators = _differentiator_entries(context, source_ideas, direct, indirect)
    gaps = _evidence_gap_entries(context, prior_art, direct, workarounds, differentiators)
    rows = _matrix_rows(direct, indirect, workarounds, differentiators)
    status = "ready" if prior_art else "fallbacks_used"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": entity_type,
            "id": entity["id"],
            "generated_at": entity.get("updated_at") or entity.get("created_at"),
        },
        "design_brief": {
            "id": entity["id"],
            "title": entity["title"],
            "domain": entity.get("domain", ""),
            "theme": entity.get("theme", ""),
            "readiness_score": float(entity.get("readiness_score") or 0.0),
            "design_status": entity.get("design_status", ""),
            "lead_idea_id": entity.get("lead_idea_id", ""),
            "source_idea_ids": _source_ids(entity, source_ideas),
        },
        "summary": {
            "status": status,
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "direct_competitor_count": len(direct),
            "indirect_alternative_count": len(indirect),
            "workaround_count": len(workarounds),
            "differentiator_count": len(differentiators),
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "competitive_context": context,
        "matrix_rows": rows,
        "competitor_entries": [
            *[
                {**competitor, "type": "direct_competitor"}
                for competitor in direct
            ],
            *[
                {**alternative, "type": "indirect_alternative"}
                for alternative in indirect
            ],
        ],
        "direct_competitors": direct,
        "indirect_alternatives": indirect,
        "workaround_entries": workarounds,
        "switching_friction_entries": friction,
        "differentiator_entries": differentiators,
        "evidence_gap_entries": gaps,
        "signals": {"prior_art": prior_art},
        "source_ideas": source_ideas,
    }


def _direct_competitors(
    prior_art: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(prior_art[:6], 1):
        risk = _substitution_risk(record["relevance_score"])
        rows.append(
            {
                "id": f"DC{index}",
                "name": record["title"],
                "category": _competitor_category(record["source"]),
                "source": record["source"],
                "url": record.get("url", ""),
                "substitution_risk": risk,
                "overlap_summary": _overlap_summary(record, context),
                "switching_friction": _friction_for_risk(risk, context),
                "differentiation_response": _differentiation_response(context, risk),
                "source_reference_ids": [record["id"], record["source_idea_id"]],
            }
        )
    if rows:
        return rows
    return [
        {
            "id": "DC0",
            "name": "Unverified direct competitor",
            "category": "unknown",
            "source": "fallback",
            "url": "",
            "substitution_risk": "unknown",
            "overlap_summary": (
                "No stored prior-art match is linked to this brief; direct alternatives "
                "must be validated before spec generation."
            ),
            "switching_friction": context["default_switching_friction"],
            "differentiation_response": (
                "Run prior-art checks and compare against the target workflow, buyer, and first MVP wedge."
            ),
            "source_reference_ids": context["source_idea_ids"],
        }
    ]


def _indirect_alternatives(
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    alternatives = [
        (
            "Status quo workflow",
            context["current_workaround"],
            "User keeps the existing process because adoption effort is lower than perceived pain.",
        ),
        (
            "Horizontal incumbent tools",
            _horizontal_tools(context),
            "Buyer extends already-approved tools instead of introducing a focused product.",
        ),
        (
            "Internal build",
            _internal_build(context, source_ideas),
            "Technical teams encode the workflow into scripts, spreadsheets, or existing internal systems.",
        ),
    ]
    rows = []
    for index, (name, behavior, why) in enumerate(alternatives, 1):
        rows.append(
            {
                "id": f"IA{index}",
                "name": name,
                "behavior": behavior,
                "substitution_risk": _indirect_risk(name, context),
                "why_users_choose_it": why,
                "switching_friction": context["default_switching_friction"],
                "differentiation_response": _indirect_response(name, context),
                "source_reference_ids": context["source_idea_ids"],
            }
        )
    return rows


def _workaround_entries(
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    values = [
        *[idea.get("current_workaround") for idea in source_ideas],
        context["current_workaround"],
    ]
    entries: list[dict[str, Any]] = []
    for value in dict.fromkeys(_string_list(values)):
        entries.append(
            {
                "id": f"WA{len(entries) + 1}",
                "behavior": value,
                "user_job": f"Complete {context['workflow_context']} without adopting a new product.",
                "switching_friction": context["default_switching_friction"],
                "source_reference_ids": context["source_idea_ids"] or ["design_brief"],
            }
        )
    if entries:
        return entries[:4]
    return [
        {
            "id": "WA0",
            "behavior": "manual process or fragmented tooling",
            "user_job": f"Complete {context['workflow_context']} with existing habits.",
            "switching_friction": "unknown until discovery confirms the current workflow.",
            "source_reference_ids": context["source_idea_ids"] or ["design_brief"],
        }
    ]


def _switching_friction_entries(context: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [
        {
            "id": "SF1",
            "factor": "Workflow migration",
            "level": "medium",
            "description": f"Users must move {context['workflow_context']} from the current workaround.",
        },
        {
            "id": "SF2",
            "factor": "Buyer approval",
            "level": "medium" if context["buyer"] != "economic buyer" else "unknown",
            "description": f"{context['buyer']} must believe the focused alternative is worth a new adoption path.",
        },
    ]
    if _has_terms(context["all_text"], ("security", "compliance", "procurement", "legal")):
        entries.append(
            {
                "id": "SF3",
                "factor": "Governance review",
                "level": "high",
                "description": "Security, compliance, procurement, or legal terms appear in the persisted inputs.",
            }
        )
    return entries


def _differentiator_entries(
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    direct: list[dict[str, Any]],
    indirect: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries = [
        {
            "id": "DF1",
            "claim": f"Built for {context['target_user']}",
            "rationale": f"Persisted inputs name {context['target_user']} as the user and {context['buyer']} as the buyer.",
            "against": [item["id"] for item in direct[:2] + indirect[:1]],
            "proof_needed": "Persona interviews showing the named user has higher pain than adjacent users.",
            "source_reference_ids": context["source_idea_ids"],
        },
        {
            "id": "DF2",
            "claim": f"Workflow-specific wedge for {context['workflow_context']}",
            "rationale": context["value_proposition"],
            "against": [item["id"] for item in direct[:2] + indirect],
            "proof_needed": "Before-and-after workflow evidence from the MVP scope or first milestone.",
            "source_reference_ids": context["source_idea_ids"],
        },
    ]
    scope = _first_text(context.get("mvp_scope"))
    if scope:
        entries.append(
            {
                "id": "DF3",
                "claim": f"Concrete MVP wedge: {_short_title(scope)}",
                "rationale": f"Use {scope} as the first point of contrast against broad tools.",
                "against": [item["id"] for item in direct[:3]],
                "proof_needed": "A task-based prototype test proving the wedge changes the buying or usage decision.",
                "source_reference_ids": context["source_idea_ids"],
            }
        )
    elif source_ideas and _first_text(source_ideas[0].get("solution")):
        entries.append(
            {
                "id": "DF3",
                "claim": f"Solution wedge: {_short_title(source_ideas[0]['solution'])}",
                "rationale": "Lead source idea includes a solution statement that can be tested as a wedge.",
                "against": [item["id"] for item in direct[:3]],
                "proof_needed": "A prototype test comparing the proposed solution to the strongest alternative.",
                "source_reference_ids": context["source_idea_ids"],
            }
        )
    return entries


def _evidence_gap_entries(
    context: dict[str, Any],
    prior_art: list[dict[str, Any]],
    direct: list[dict[str, Any]],
    workarounds: list[dict[str, Any]],
    differentiators: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not prior_art:
        gaps.append(
            {
                "id": "EG1",
                "gap": "No stored prior-art matches",
                "resolution": "Run and persist prior-art checks for the source ideas before treating direct competition as known.",
                "owner": "Product strategy",
                "source_reference_ids": context["source_idea_ids"],
            }
        )
    if "current_workaround" in context["fallbacks_used"]:
        gaps.append(
            {
                "id": f"EG{len(gaps) + 1}",
                "gap": "Current workaround is inferred",
                "resolution": "Interview target users and persist the actual workaround behavior on the source idea or design brief.",
                "owner": "Discovery",
                "source_reference_ids": context["source_idea_ids"],
            }
        )
    if "target_user" in context["fallbacks_used"] or "buyer" in context["fallbacks_used"]:
        gaps.append(
            {
                "id": f"EG{len(gaps) + 1}",
                "gap": "Persona or buyer evidence is sparse",
                "resolution": "Confirm the user, buyer, and switching authority before spec generation.",
                "owner": "Product",
                "source_reference_ids": context["source_idea_ids"],
            }
        )
    gaps.append(
        {
            "id": f"EG{len(gaps) + 1}",
            "gap": "Differentiator proof is not yet decisive",
            "resolution": (
                f"Validate {differentiators[0]['claim']} against "
                f"{direct[0]['name']} and {workarounds[0]['behavior']}."
            ),
            "owner": "Validation",
            "source_reference_ids": context["source_idea_ids"],
        }
    )
    return gaps


def _matrix_rows(
    direct: list[dict[str, Any]],
    indirect: list[dict[str, Any]],
    workarounds: list[dict[str, Any]],
    differentiators: list[dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for competitor in direct:
        rows.append(
            {
                "type": "Direct competitor",
                "alternative": competitor["name"],
                "substitution_risk": competitor["substitution_risk"],
                "switching_friction": competitor["switching_friction"],
                "differentiation_response": competitor["differentiation_response"],
                "evidence": _inline_ids(competitor["source_reference_ids"]),
            }
        )
    for alternative in indirect:
        rows.append(
            {
                "type": "Indirect alternative",
                "alternative": alternative["name"],
                "substitution_risk": alternative["substitution_risk"],
                "switching_friction": alternative["switching_friction"],
                "differentiation_response": alternative["differentiation_response"],
                "evidence": _inline_ids(alternative["source_reference_ids"]),
            }
        )
    rows.append(
        {
            "type": "Current workaround",
            "alternative": workarounds[0]["behavior"],
            "substitution_risk": "medium",
            "switching_friction": workarounds[0]["switching_friction"],
            "differentiation_response": differentiators[0]["claim"],
            "evidence": _inline_ids(workarounds[0]["source_reference_ids"]),
        }
    )
    return rows


def _context_from_brief(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    target_user = _first_with_fallback(
        fallbacks,
        "target_user",
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        f"{title} user",
    )
    buyer = _first_with_fallback(
        fallbacks,
        "buyer",
        design_brief.get("buyer"),
        _field_values(source_ideas, "buyer"),
        "economic buyer",
    )
    workflow = _first_with_fallback(
        fallbacks,
        "workflow_context",
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        f"{title} workflow",
    )
    value = _first_with_fallback(
        fallbacks,
        "value_proposition",
        _field_values(source_ideas, "value_proposition"),
        design_brief.get("merged_product_concept"),
        f"Improve {workflow}",
    )
    workaround = _first_with_fallback(
        fallbacks,
        "current_workaround",
        _field_values(source_ideas, "current_workaround"),
        "manual process or fragmented tooling",
    )
    all_text = _compact(
        " ".join(
            _string_list(
                [
                    design_brief.get("title"),
                    design_brief.get("domain"),
                    design_brief.get("theme"),
                    design_brief.get("why_this_now"),
                    design_brief.get("merged_product_concept"),
                    design_brief.get("synthesis_rationale"),
                    design_brief.get("validation_plan"),
                    design_brief.get("risks"),
                    *[
                        idea.get(field)
                        for idea in source_ideas
                        for field in (
                            "title",
                            "problem",
                            "solution",
                            "value_proposition",
                            "workflow_context",
                            "current_workaround",
                            "domain_risks",
                        )
                    ],
                ]
            )
        )
    ).lower()
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "value_proposition": value,
        "current_workaround": workaround,
        "mvp_scope": _string_list(design_brief.get("mvp_scope")),
        "first_milestones": _string_list(design_brief.get("first_milestones")),
        "source_idea_ids": [idea["id"] for idea in source_ideas]
        or _string_list(design_brief.get("source_idea_ids")),
        "default_switching_friction": _default_switching_friction(workaround, all_text),
        "fallbacks_used": fallbacks,
        "all_text": all_text,
    }


def _context_from_unit(unit: dict[str, Any]) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = _first_text(unit.get("title"), "Untitled buildable unit")
    target_user = _first_with_fallback(fallbacks, "target_user", unit.get("specific_user"), f"{title} user")
    buyer = _first_with_fallback(fallbacks, "buyer", unit.get("buyer"), "economic buyer")
    workflow = _first_with_fallback(
        fallbacks,
        "workflow_context",
        unit.get("workflow_context"),
        f"{title} workflow",
    )
    value = _first_with_fallback(
        fallbacks,
        "value_proposition",
        unit.get("value_proposition"),
        unit.get("solution"),
        f"Improve {workflow}",
    )
    workaround = _first_with_fallback(
        fallbacks,
        "current_workaround",
        unit.get("current_workaround"),
        "manual process or fragmented tooling",
    )
    all_text = _compact(
        " ".join(
            _string_list(
                [
                    unit.get("title"),
                    unit.get("problem"),
                    unit.get("solution"),
                    unit.get("value_proposition"),
                    unit.get("workflow_context"),
                    unit.get("current_workaround"),
                    unit.get("domain_risks"),
                ]
            )
        )
    ).lower()
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "value_proposition": value,
        "current_workaround": workaround,
        "mvp_scope": [],
        "first_milestones": [],
        "source_idea_ids": [unit["id"]],
        "default_switching_friction": _default_switching_friction(workaround, all_text),
        "fallbacks_used": fallbacks,
        "all_text": all_text,
    }


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id: dict[str, dict[str, Any]] = {}
    for source in design_brief.get("sources", []):
        relationship_by_id.setdefault(source["idea_id"], source)

    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *design_brief.get("source_idea_ids", []),
                *relationship_by_id.keys(),
            ]
        )
    )
    ideas: list[dict[str, Any]] = []
    for idea_id in ordered_ids:
        if not idea_id:
            continue
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            continue
        data = unit.model_dump(mode="json")
        relationship = relationship_by_id.get(str(idea_id), {})
        data["role"] = relationship.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _prior_art_records(store: Store, source_ids: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idea_id in source_ids:
        for match in store.get_prior_art_matches(idea_id):
            records.append(
                {
                    "id": match["id"],
                    "source_idea_id": idea_id,
                    "source": match["source"],
                    "title": match["title"],
                    "url": match["url"],
                    "description": match.get("description", ""),
                    "relevance_score": round(float(match.get("relevance_score") or 0.0), 3),
                    "match_signals": match.get("match_signals", {}),
                    "search_query": match.get("search_query", ""),
                    "created_at": match.get("created_at", ""),
                }
            )
    records.sort(key=lambda item: (-item["relevance_score"], item["source"], item["title"], item["id"]))
    return records


def _source_ids(entity: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    return [idea["id"] for idea in source_ideas] or _string_list(entity.get("source_idea_ids"))


def _field_values(records: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for record in records:
        values.extend(_string_list(record.get(field)))
    return values


def _first_with_fallback(fallbacks: list[str], label: str, *values: Any) -> str:
    for value in values[:-1]:
        text = _first_text(value)
        if text:
            return text
    fallbacks.append(label)
    return _first_text(values[-1], "")


def _first_text(*values: Any) -> str:
    for value in values:
        items = _string_list(value)
        if items:
            return items[0]
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return result
    if isinstance(value, tuple | set):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_string_list(item))
        return result
    text = str(value).strip()
    return [text] if text else []


def _substitution_risk(score: float) -> str:
    if score >= 0.82:
        return "high"
    if score >= 0.62:
        return "medium"
    return "low"


def _competitor_category(source: str) -> str:
    return {
        "github": "open_source",
        "npm": "developer_package",
        "pypi": "developer_package",
        "product_hunt": "product",
    }.get(str(source).lower(), "prior_art")


def _overlap_summary(record: dict[str, Any], context: dict[str, Any]) -> str:
    description = _first_text(record.get("description"), record.get("search_query"))
    if description:
        return _compact(description)
    return f"Stored match overlaps with {context['workflow_context']}."


def _friction_for_risk(risk: str, context: dict[str, Any]) -> str:
    if risk == "high":
        return "high if the incumbent is already approved or embedded in the workflow."
    if risk == "medium":
        return context["default_switching_friction"]
    return "low to medium; validate whether the alternative is actively used."


def _differentiation_response(context: dict[str, Any], risk: str) -> str:
    if risk == "high":
        return f"Narrow the wedge to {context['target_user']} and prove superior fit for {context['workflow_context']}."
    return f"Use {context['value_proposition']} as the comparison point."


def _horizontal_tools(context: dict[str, Any]) -> str:
    if _has_terms(context["all_text"], ("spreadsheet", "sheets", "excel")):
        return "spreadsheets and shared documents"
    if _has_terms(context["all_text"], ("slack", "email", "ticket", "jira", "linear")):
        return "collaboration, ticketing, or messaging tools"
    return "general-purpose productivity and collaboration tools"


def _internal_build(context: dict[str, Any], source_ideas: list[dict[str, Any]]) -> str:
    stack_terms = []
    for idea in source_ideas:
        stack_terms.extend(_string_list(idea.get("suggested_stack")))
    if stack_terms:
        return f"internal build using {', '.join(stack_terms[:3])}"
    return f"internal automation for {context['workflow_context']}"


def _indirect_risk(name: str, context: dict[str, Any]) -> str:
    if name == "Status quo workflow":
        return "high" if context["current_workaround"] else "unknown"
    if name == "Horizontal incumbent tools":
        return "medium"
    return "medium" if _has_terms(context["all_text"], ("api", "automation", "script", "internal")) else "low"


def _indirect_response(name: str, context: dict[str, Any]) -> str:
    if name == "Status quo workflow":
        return f"Prove the pain of staying with {context['current_workaround']}."
    if name == "Horizontal incumbent tools":
        return f"Show why a focused {context['workflow_context']} workflow beats generic tooling."
    return "Validate build-versus-buy urgency, maintenance burden, and time-to-value."


def _default_switching_friction(workaround: str, text: str) -> str:
    if _has_terms(text, ("procurement", "legal", "security", "compliance", "migration")):
        return "high because adoption likely needs governance, migration, or approval work."
    if _has_terms(workaround.lower(), ("spreadsheet", "manual", "email", "slack", "ticket")):
        return "medium because users must replace familiar manual or horizontal-tool habits."
    return "medium until workflow ownership and adoption cost are validated."


def _has_terms(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _short_title(text: str, *, max_chars: int = 64) -> str:
    compact = _compact(text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _compact(text: str) -> str:
    return " ".join(str(text).split())


def _filename_part(value: str) -> str:
    return "-".join(re.findall(r"[A-Za-z0-9]+", value)).strip("-") or "design-brief"


def _inline_ids(ids: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in ids if item) or "`design_brief`"
