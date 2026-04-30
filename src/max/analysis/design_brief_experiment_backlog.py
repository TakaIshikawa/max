"""Deterministic experiment backlogs for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.experiment_backlog"
SCHEMA_VERSION = "max.design_brief.experiment_backlog.v1"

_HIGH_RISK_TERMS = (
    "compliance",
    "credential",
    "legal",
    "pii",
    "privacy",
    "regulated",
    "security",
)


def build_design_brief_experiment_backlog(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a prioritized validation experiment backlog from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _experiment_context(design_brief, source_ideas, lead_idea)
    evidence_refs = _evidence_references(design_brief, source_ideas)
    gaps = _evidence_gaps(design_brief, context, source_idea_ids, evidence_refs)
    backlog_items = _prioritized_items(
        design_brief,
        source_ideas,
        context,
        source_idea_ids,
        evidence_refs,
        gaps,
    )

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
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
            "summary": context["summary"],
        },
        "summary": {
            "backlog_item_count": len(backlog_items),
            "source_idea_count": len(source_idea_ids),
            "evidence_reference_count": len(evidence_refs),
            "evidence_gap_count": len(gaps),
            "top_priority_score": backlog_items[0]["priority_score"] if backlog_items else 0,
            "fallbacks_used": context["fallbacks_used"],
        },
        "backlog_items": backlog_items,
        "evidence_references": evidence_refs,
        "evidence_gaps": gaps,
        "recommended_next_actions": _recommended_next_actions(backlog_items, gaps),
        "source_ideas": source_ideas,
    }


def render_design_brief_experiment_backlog(report: dict[str, Any], fmt: str = "json") -> str:
    """Render an experiment backlog as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported experiment backlog format: {fmt}")

    brief = report["design_brief"]
    lines = [
        f"# Experiment Backlog: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Design Brief Summary",
        "",
        brief["summary"],
        "",
        "## Prioritized Experiments",
        "",
    ]

    for item in report["backlog_items"]:
        lines.extend(
            [
                f"### {item['rank']}. {item['title']}",
                "",
                f"- Hypothesis: {item['hypothesis']}",
                f"- Experiment type: {item['experiment_type']}",
                f"- Target persona: {item['target_persona']}",
                f"- Required evidence: {', '.join(item['required_evidence'])}",
                f"- Success metric: {item['success_metric']}",
                f"- Effort: {item['effort']}",
                f"- Risk reduction: {item['risk_reduction']}",
                f"- Priority score: {item['priority_score']}",
                f"- Source idea references: {', '.join(item['source_idea_ids']) or 'design brief'}",
                "",
            ]
        )

    lines.extend(["## Evidence Gaps", ""])
    if report["evidence_gaps"]:
        for gap in report["evidence_gaps"]:
            lines.append(f"- **{gap['id']}** ({gap['field']}): {gap['gap']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Recommended Next Actions", ""])
    if report["recommended_next_actions"]:
        for action in report["recommended_next_actions"]:
            lines.append(f"- **{action['id']}**: {action['action']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def experiment_backlog_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for an experiment backlog export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "experiment-backlog"))
    return f"{brief_id}-{title}-experiment-backlog.{extension}"


def _prioritized_items(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_refs: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    all_sources = source_idea_ids

    _add_item(
        items,
        design_brief,
        evidence_refs,
        gaps,
        title="Validate target workflow and buyer urgency",
        hypothesis=(
            f"{context['target_persona']} has urgent enough pain in {context['workflow_context']} "
            f"to justify {context['title']}."
        ),
        experiment_type="customer discovery",
        target_persona=context["target_persona"],
        required_evidence=[
            "5 structured interviews",
            "documented current workaround",
            "buyer decision trigger",
        ],
        success_metric="4 of 5 qualified conversations confirm the workflow, pain severity, and buying trigger.",
        effort="medium",
        risk_reduction="high",
        source_idea_ids=_source_ids_for_lead(source_ideas, all_sources),
        source_fields=["specific_user", "buyer", "workflow_context", "why_this_now"],
        urgency="high" if context["fallbacks_used"] else "medium",
    )

    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    for risk in risks[:3]:
        _add_item(
            items,
            design_brief,
            evidence_refs,
            gaps,
            title=f"De-risk {_short_title(risk)}",
            hypothesis=f"The team can mitigate this risk before build commitment: {risk}",
            experiment_type=_experiment_type_for_risk(risk),
            target_persona=_persona_for_risk(risk, context),
            required_evidence=[
                "risk owner review",
                "explicit proceed or stop threshold",
                "mitigation evidence",
            ],
            success_metric="Risk owner accepts a mitigation plan with a written threshold for proceeding.",
            effort="medium" if _risk_weight(risk) < 25 else "high",
            risk_reduction="high",
            source_idea_ids=_source_ids_for_text(risk, source_ideas, all_sources),
            source_fields=["risks", "domain_risks"],
            urgency="high",
            risk_text=risk,
        )

    for scope in _string_list(design_brief.get("mvp_scope"))[:3]:
        _add_item(
            items,
            design_brief,
            evidence_refs,
            gaps,
            title=f"Test MVP scope: {scope}",
            hypothesis=f"{context['target_persona']} can complete {scope} and recognize concrete workflow value.",
            experiment_type="prototype usability test",
            target_persona=context["target_persona"],
            required_evidence=[
                "clickable or concierge prototype",
                "task completion observations",
                "friction notes",
            ],
            success_metric="3 of 5 target users complete the task and identify the output as useful.",
            effort="medium",
            risk_reduction="medium",
            source_idea_ids=_source_ids_for_text(scope, source_ideas, all_sources),
            source_fields=["mvp_scope", "solution", "tech_approach"],
            urgency="medium",
        )

    _add_item(
        items,
        design_brief,
        evidence_refs,
        gaps,
        title="Run validation-plan smoke test",
        hypothesis=f"The persisted validation plan can produce a clear build, revise, or stop decision for {context['title']}.",
        experiment_type="validation smoke test",
        target_persona=context["target_persona"],
        required_evidence=[
            "written pass/fail rubric",
            "pilot participant list",
            "decision log",
        ],
        success_metric=context["validation_plan_metric"],
        effort="low" if _first_text(design_brief.get("validation_plan")) else "medium",
        risk_reduction="high",
        source_idea_ids=all_sources,
        source_fields=["validation_plan", "readiness_score"],
        urgency="high" if not _first_text(design_brief.get("validation_plan")) else "medium",
    )

    if len(items) < 3:
        _add_item(
            items,
            design_brief,
            evidence_refs,
            gaps,
            title="Create source-evidence audit",
            hypothesis="A short evidence audit can identify the minimum proof needed before implementation planning.",
            experiment_type="evidence audit",
            target_persona="product lead",
            required_evidence=[
                "source idea inventory",
                "assumption list",
                "ranked evidence gaps",
            ],
            success_metric="Every critical assumption has an owner, evidence request, and validation method.",
            effort="low",
            risk_reduction="medium",
            source_idea_ids=all_sources,
            source_fields=["source_idea_ids", "readiness_score"],
            urgency="high",
        )

    ranked = sorted(
        items, key=lambda item: (-item["priority_score"], _effort_rank(item["effort"]), item["id"])
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


def _add_item(
    items: list[dict[str, Any]],
    design_brief: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    *,
    title: str,
    hypothesis: str,
    experiment_type: str,
    target_persona: str,
    required_evidence: list[str],
    success_metric: str,
    effort: str,
    risk_reduction: str,
    source_idea_ids: list[str],
    source_fields: list[str],
    urgency: str,
    risk_text: str = "",
) -> None:
    source_ids = list(dict.fromkeys(source_idea_ids))
    item_id = f"EXP{len(items) + 1}"
    breakdown = _priority_breakdown(
        design_brief,
        evidence_refs,
        gaps,
        source_ids,
        source_fields,
        effort,
        risk_reduction,
        urgency,
        risk_text,
    )
    items.append(
        {
            "id": item_id,
            "rank": 0,
            "title": title,
            "hypothesis": hypothesis,
            "experiment_type": experiment_type,
            "target_persona": target_persona,
            "required_evidence": required_evidence,
            "success_metric": success_metric,
            "effort": effort,
            "risk_reduction": risk_reduction,
            "priority_score": breakdown["total"],
            "priority_breakdown": breakdown,
            "source_idea_ids": source_ids,
            "source_fields": source_fields,
            "recommended_next_actions": [
                f"Assign an owner for {experiment_type}.",
                "Collect the required evidence and record a build, revise, or stop decision.",
            ],
        }
    )


def _priority_breakdown(
    design_brief: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    source_ids: list[str],
    source_fields: list[str],
    effort: str,
    risk_reduction: str,
    urgency: str,
    risk_text: str,
) -> dict[str, int]:
    gap_fields = {gap["field"] for gap in gaps}
    missing_fields = sum(1 for field in source_fields if field in gap_fields)
    has_evidence = bool(evidence_refs) and bool(source_ids)
    evidence_gap = min(35, 12 + missing_fields * 7 + (0 if has_evidence else 12))
    risk = {"low": 8, "medium": 15, "high": 22}.get(risk_reduction, 15)
    risk = max(risk, _risk_weight(risk_text))
    readiness = max(
        0, min(20, round((70.0 - float(design_brief.get("readiness_score") or 0.0)) / 70.0 * 20))
    )
    validation_urgency = {"low": 6, "medium": 13, "high": 20}.get(urgency, 13)
    effort_penalty = {"low": 0, "medium": 4, "high": 8}.get(effort, 4)
    total = max(0, min(100, evidence_gap + risk + readiness + validation_urgency - effort_penalty))
    return {
        "evidence_gap": evidence_gap,
        "risk": risk,
        "readiness": readiness,
        "validation_urgency": validation_urgency,
        "effort_penalty": effort_penalty,
        "total": total,
    }


def _experiment_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        ("target user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("economic buyer", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        lead_idea and lead_idea.get("value_proposition"),
        f"Validate {title}.",
    )
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Run the smallest validation that can produce a written proceed, revise, or stop decision.",
    )
    return {
        "title": title,
        "target_persona": user,
        "buyer": buyer,
        "workflow_context": workflow,
        "concept": concept,
        "validation_plan_metric": (
            validation_plan if validation_plan.endswith(".") else f"{validation_plan}."
        ),
        "summary": f"{title} targets {user} in {workflow}, with {buyer} as the buying or approval path.",
        "fallbacks_used": fallbacks,
    }


def _evidence_gaps(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    checks = [
        ("specific_user", "Target persona is not explicit in the persisted brief."),
        ("buyer", "Buyer or approval path is not explicit in the persisted brief."),
        ("workflow_context", "Workflow context is not explicit enough for validation recruiting."),
        ("mvp_scope", "MVP scope is not decomposed into testable workflow slices."),
        ("validation_plan", "Validation plan is missing or not actionable."),
    ]
    for field, gap in checks:
        missing = not _string_list(design_brief.get(field)) or field in context["fallbacks_used"]
        if missing:
            gaps.append({"id": f"G{len(gaps) + 1}", "field": field, "gap": gap})

    if not source_idea_ids:
        gaps.append(
            {
                "id": f"G{len(gaps) + 1}",
                "field": "source_idea_ids",
                "gap": "No source idea references are available for traceability.",
            }
        )
    if not evidence_refs:
        gaps.append(
            {
                "id": f"G{len(gaps) + 1}",
                "field": "evidence_references",
                "gap": "No evidence signals, insights, rationale, or validation text support the brief.",
            }
        )
    return gaps


def _recommended_next_actions(
    items: list[dict[str, Any]], gaps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in items[:3]:
        actions.append(
            {
                "id": f"NA{len(actions) + 1}",
                "experiment_id": item["id"],
                "action": f"Run `{item['id']}` next: {item['title']}.",
            }
        )
    for gap in gaps[:2]:
        actions.append(
            {
                "id": f"NA{len(actions) + 1}",
                "gap_id": gap["id"],
                "action": f"Resolve evidence gap `{gap['field']}` before broad build commitment.",
            }
        )
    return actions


def _evidence_references(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
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
                    "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
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
                    "summary": f"Evidence signal linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "summary": f"Inspiring insight linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
    return _dedupe_refs(refs)


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


def _source_ids_for_lead(source_ideas: list[dict[str, Any]], fallback: list[str]) -> list[str]:
    lead = next(
        (idea for idea in source_ideas if idea.get("role") == "lead" and not idea.get("missing")),
        None,
    )
    if lead:
        return [lead["id"]]
    return fallback


def _source_ids_for_text(
    text: str, source_ideas: list[dict[str, Any]], fallback: list[str]
) -> list[str]:
    tokens = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 3}
    matches: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        haystack = " ".join(
            str(idea.get(field) or "")
            for field in (
                "title",
                "one_liner",
                "problem",
                "solution",
                "tech_approach",
                "value_proposition",
                "domain_risks",
            )
        ).lower()
        if tokens and tokens & set(re.findall(r"[a-z0-9]+", haystack)):
            matches.append(idea["id"])
    return matches or fallback


def _experiment_type_for_risk(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _HIGH_RISK_TERMS):
        return "expert review"
    if any(term in lowered for term in ("api", "data", "integration", "latency", "technical")):
        return "technical spike"
    if any(term in lowered for term in ("adoption", "buyer", "market", "pricing")):
        return "market validation"
    return "risk probe"


def _persona_for_risk(risk: str, context: dict[str, Any]) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _HIGH_RISK_TERMS):
        return "risk reviewer"
    if any(term in lowered for term in ("buyer", "market", "pricing", "adoption")):
        return context["buyer"]
    return context["target_persona"]


def _risk_weight(risk: str) -> int:
    lowered = risk.lower()
    if any(term in lowered for term in _HIGH_RISK_TERMS):
        return 25
    if any(
        term in lowered for term in ("adoption", "integration", "latency", "market", "technical")
    ):
        return 20
    return 0


def _effort_rank(effort: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(effort, 1)


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
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


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault(ref["id"], ref)
    return list(deduped.values())


def _short_title(text: str) -> str:
    stripped = _compact(text).rstrip(".")
    if len(stripped) <= 72:
        return stripped
    return stripped[:69].rstrip() + "..."


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
