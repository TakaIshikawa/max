"""Deterministic renewal and expansion plans for persisted design briefs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.renewal_expansion_plan.v1"
KIND = "max.design_brief.renewal_expansion_plan"

_VALIDATED_STATUSES = {"approved", "validated", "ready", "launched", "active"}
_WEAK_STATUSES = {"draft", "candidate", "proposed", "backlog", "new"}

_RENEWAL_RISK_TERMS = (
    "budget",
    "churn",
    "compliance",
    "dependency",
    "handoff",
    "integration",
    "legal",
    "manual",
    "migration",
    "procurement",
    "security",
    "support",
    "ticket",
)
_EXPANSION_TERMS = (
    "automation",
    "department",
    "enterprise",
    "integration",
    "multi-team",
    "platform",
    "recurring",
    "rollout",
    "team",
    "weekly",
    "workflow",
)
_PROOF_TERMS = (
    "activation",
    "evidence",
    "interview",
    "metric",
    "pilot",
    "proof",
    "renewal",
    "retention",
    "survey",
    "validation",
)


def build_design_brief_renewal_expansion_plan(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a post-launch renewal and expansion plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    evidence_signals = _evidence_signals(store, source_ideas)
    readiness_context = _readiness_context(store, design_brief, source_ideas)
    context = _plan_context(design_brief, source_ideas, evidence_signals, readiness_context)
    missing_inputs = _missing_inputs(context, design_brief, source_idea_ids)
    renewal_risks = _renewal_risks(context, source_idea_ids, missing_inputs)
    expansion_triggers = _expansion_triggers(context, source_idea_ids)
    expansion_opportunities = _expansion_opportunities(context, expansion_triggers, source_idea_ids)
    customer_success_motions = _customer_success_motions(context, renewal_risks)
    proof_points = _proof_points(context, evidence_signals, readiness_context, source_idea_ids)
    next_actions = _next_actions(context, renewal_risks, expansion_opportunities, proof_points)

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
            "buyer": context["buyer"],
            "specific_user": context["specific_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "renewal_health": _renewal_health(
                design_brief,
                renewal_risks,
                proof_points,
                missing_inputs,
            ),
            "renewal_risk_count": len(renewal_risks),
            "expansion_opportunity_count": len(expansion_opportunities),
            "proof_point_count": len(proof_points),
            "next_action_count": len(next_actions),
            "missing_input_count": len(missing_inputs),
            "source_idea_count": len(source_idea_ids),
            "evidence_signal_count": len(evidence_signals),
            "fallbacks_used": context["fallbacks_used"],
        },
        "renewal_context": context,
        "renewal_risks": renewal_risks,
        "expansion_triggers": expansion_triggers,
        "expansion_opportunities": expansion_opportunities,
        "customer_success_motions": customer_success_motions,
        "proof_points": proof_points,
        "next_actions": next_actions,
        "missing_inputs": missing_inputs,
        "evidence_signals": evidence_signals,
        "readiness_context": readiness_context,
        "source_ideas": source_ideas,
    }


def render_design_brief_renewal_expansion_plan(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a renewal and expansion plan as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported renewal expansion plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Renewal and Expansion Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Design brief: `{brief['id']}`",
        f"Renewal health: `{summary['renewal_health']}`",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Workflow: {brief['workflow_context']}",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
        "## Renewal Risks",
        "",
    ]
    for risk in report["renewal_risks"]:
        lines.extend(
            [
                f"- **{risk['risk']}** (`{risk['severity']}`): {risk['reason']}",
                f"  Mitigation: {risk['mitigation']}",
                f"  Source references: {_inline_ids(risk['source_reference_ids'])}",
            ]
        )

    lines.extend(["", "## Expansion Opportunities", ""])
    for opportunity in report["expansion_opportunities"]:
        lines.extend(
            [
                f"- **{opportunity['opportunity']}** (`{opportunity['confidence']}`): {opportunity['why_it_matters']}",
                f"  Trigger: {opportunity['trigger']}",
                f"  Proof needed: {opportunity['proof_needed']}",
            ]
        )

    lines.extend(["", "## Customer Success Motions", ""])
    for motion in report["customer_success_motions"]:
        lines.extend(
            [
                f"- **{motion['motion']}** ({motion['owner_role']}): {motion['cadence']}",
                f"  Success evidence: {motion['success_evidence']}",
            ]
        )

    lines.extend(["", "## Proof Points", ""])
    for proof in report["proof_points"]:
        lines.append(
            f"- **{proof['claim']}** (`{proof['strength']}`): {proof['evidence']} "
            f"[{_inline_ids(proof['source_reference_ids'])}]"
        )

    lines.extend(["", "## Next Actions", ""])
    for action in report["next_actions"]:
        lines.append(
            f"- **{action['owner_role']}**: {action['action']} "
            f"(due: {action['timing']}; addresses: {action['addresses']})"
        )

    lines.extend(["", "## Missing Inputs", ""])
    if report["missing_inputs"]:
        for item in report["missing_inputs"]:
            lines.append(f"- **{item['field']}**: {item['warning']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def write_design_brief_renewal_expansion_plan(
    path: Path,
    report: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_design_brief_renewal_expansion_plan(report, fmt=fmt),
        encoding="utf-8",
    )


def renewal_expansion_plan_filename(
    design_brief: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'renewal-expansion-plan'))}-"
        f"renewal-expansion-plan.{extension}"
    )


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


def _source_idea_ids(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[str]:
    ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    return ids or _string_list(design_brief.get("source_idea_ids"))


def _evidence_signals(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            if signal_id in seen:
                continue
            seen.add(signal_id)
            signal = store.get_signal(signal_id)
            if signal:
                data = signal.model_dump(mode="json")
                records.append(
                    {
                        "id": data["id"],
                        "type": "signal",
                        "title": data.get("title", ""),
                        "description": data.get("content", ""),
                        "credibility": float(data.get("credibility") or 0.0),
                        "tags": _string_list(data.get("tags")),
                        "url": data.get("url", ""),
                    }
                )
            else:
                records.append(
                    {
                        "id": signal_id,
                        "type": "missing_signal",
                        "title": "",
                        "description": "",
                        "credibility": 0.0,
                        "tags": [],
                        "url": "",
                    }
                )
    records.sort(key=lambda item: item["id"])
    return records


def _readiness_context(
    store: Store,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        evaluation = store.get_evaluation(str(idea["id"]))
        if not evaluation:
            continue
        evaluations.append(evaluation.model_dump(mode="json"))

    strengths = _dedupe(
        [
            text
            for evaluation in evaluations
            for text in _string_list(evaluation.get("strengths"))
        ]
    )
    weaknesses = _dedupe(
        [
            text
            for evaluation in evaluations
            for text in _string_list(evaluation.get("weaknesses"))
        ]
    )
    recommendations = _dedupe(
        [
            evaluation.get("recommendation", "")
            for evaluation in evaluations
            if _has_value(evaluation.get("recommendation"))
        ]
    )
    readiness_score = float(design_brief.get("readiness_score") or 0.0)
    status = str(design_brief.get("design_status") or "").lower()
    return {
        "readiness_score": readiness_score,
        "design_status": status,
        "readiness_band": _readiness_band(readiness_score, status),
        "evaluation_count": len(evaluations),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations,
    }


def _plan_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_signals: list[dict[str, Any]],
    readiness_context: dict[str, Any],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief.get("title") or "Untitled Design Brief")
    buyer = _first_with_fallback(
        fallbacks,
        "buyer",
        design_brief.get("buyer"),
        _field_values(source_ideas, "buyer"),
        fallback="renewal owner",
    )
    user = _first_with_fallback(
        fallbacks,
        "specific_user",
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        fallback=f"{title} user",
    )
    workflow = _first_with_fallback(
        fallbacks,
        "workflow_context",
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        fallback=f"{title} workflow",
    )
    value = _first_with_fallback(
        fallbacks,
        "value_proposition",
        design_brief.get("merged_product_concept"),
        _field_values(source_ideas, "value_proposition"),
        _field_values(source_ideas, "solution"),
        fallback=f"Improve {workflow}.",
    )
    validation_plan = _first_with_fallback(
        fallbacks,
        "validation_plan",
        design_brief.get("validation_plan"),
        _field_values(source_ideas, "validation_plan"),
        fallback="Define renewal proof metrics before the first customer review.",
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    if not scope:
        fallbacks.append("mvp_scope")
    milestones = _string_list(design_brief.get("first_milestones"))
    if not milestones:
        fallbacks.append("first_milestones")
    risks = _dedupe(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    first_customers = _first_text(
        design_brief.get("first_10_customers"),
        _field_values(source_ideas, "first_10_customers"),
    )
    current_workaround = _first_text(
        design_brief.get("current_workaround"),
        _field_values(source_ideas, "current_workaround"),
        "the current manual workflow",
    )
    text = " ".join(
        _string_list(
            [
                design_brief.get("title"),
                design_brief.get("domain"),
                design_brief.get("theme"),
                design_brief.get("why_this_now"),
                design_brief.get("merged_product_concept"),
                design_brief.get("synthesis_rationale"),
                design_brief.get("mvp_scope"),
                design_brief.get("first_milestones"),
                design_brief.get("validation_plan"),
                design_brief.get("risks"),
                first_customers,
                current_workaround,
                readiness_context.get("strengths"),
                readiness_context.get("weaknesses"),
                readiness_context.get("recommendations"),
                *[
                    idea.get(field)
                    for idea in source_ideas
                    for field in (
                        "problem",
                        "solution",
                        "value_proposition",
                        "buyer",
                        "workflow_context",
                        "current_workaround",
                        "why_now",
                        "validation_plan",
                        "first_10_customers",
                        "domain_risks",
                        "evidence_rationale",
                    )
                ],
                *[
                    signal.get(field)
                    for signal in evidence_signals
                    for field in ("title", "description", "tags")
                ],
            ]
        )
    ).lower()
    return {
        "buyer": buyer,
        "specific_user": user,
        "workflow_context": workflow,
        "value_proposition": value,
        "validation_plan": validation_plan,
        "mvp_scope": scope,
        "first_milestones": milestones,
        "risks": risks,
        "first_customers": first_customers,
        "current_workaround": current_workaround,
        "readiness_band": readiness_context["readiness_band"],
        "text": text,
        "renewal_terms": _matched_terms(text, _RENEWAL_RISK_TERMS),
        "expansion_terms": _matched_terms(text, _EXPANSION_TERMS),
        "proof_terms": _matched_terms(text, _PROOF_TERMS),
        "fallbacks_used": fallbacks,
    }


def _missing_inputs(
    context: dict[str, Any],
    design_brief: dict[str, Any],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    checks = [
        ("buyer", "Add the economic buyer or renewal approver."),
        ("specific_user", "Add the day-to-day user persona."),
        ("workflow_context", "Describe the recurring workflow that should renew."),
        ("value_proposition", "Describe the business value that should justify renewal."),
        ("validation_plan", "Define the proof plan for renewal and expansion value."),
        ("mvp_scope", "List the MVP scope that customer success can onboard."),
        ("first_milestones", "List first milestones for post-launch value tracking."),
    ]
    missing = [
        {
            "field": field,
            "warning": warning,
            "source_reference_ids": source_idea_ids,
        }
        for field, warning in checks
        if field in context["fallbacks_used"]
    ]
    if not source_idea_ids:
        missing.append(
            {
                "field": "source_idea_ids",
                "warning": "No source ideas are linked to support renewal planning.",
                "source_reference_ids": [],
            }
        )
    if not _string_list(design_brief.get("risks")) and not context["risks"]:
        missing.append(
            {
                "field": "risks",
                "warning": "No renewal, onboarding, support, or commercial risks are documented.",
                "source_reference_ids": source_idea_ids,
            }
        )
    return missing


def _renewal_risks(
    context: dict[str, Any],
    source_idea_ids: list[str],
    missing_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if missing_inputs:
        risks.append(
            {
                "id": "RR0",
                "risk": "Core renewal inputs are incomplete",
                "severity": "high",
                "reason": f"Missing persisted fields: {', '.join(item['field'] for item in missing_inputs)}.",
                "mitigation": "Complete the brief before using this plan for renewal forecasting.",
                "source_reference_ids": source_idea_ids,
            }
        )

    for risk in context["risks"][:3]:
        risks.append(
            {
                "id": f"RR{len(risks) + 1}",
                "risk": risk,
                "severity": "high" if _contains_any(risk, _RENEWAL_RISK_TERMS) else "medium",
                "reason": "Persisted risk item can affect adoption, renewal confidence, or account health.",
                "mitigation": "Convert this risk into an owner, monitoring signal, and customer-facing mitigation.",
                "source_reference_ids": source_idea_ids,
            }
        )

    if context["readiness_band"] != "ready":
        risks.append(
            {
                "id": f"RR{len(risks) + 1}",
                "risk": "Renewal plan depends on unresolved readiness work",
                "severity": "medium" if context["readiness_band"] == "partial" else "high",
                "reason": f"Readiness band is {context['readiness_band']}.",
                "mitigation": "Hold expansion asks until activation, support handoff, and value proof are stable.",
                "source_reference_ids": source_idea_ids,
            }
        )

    if not risks:
        risks.append(
            {
                "id": "RR1",
                "risk": "No major renewal risk is visible in the persisted brief",
                "severity": "low",
                "reason": "The brief has buyer, user, workflow, value, and readiness context.",
                "mitigation": "Monitor activation, value proof, and support load during the first renewal cycle.",
                "source_reference_ids": source_idea_ids,
            }
        )
    return risks


def _expansion_triggers(
    context: dict[str, Any],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    triggers = [
        {
            "id": "ET1",
            "trigger": "Repeated workflow success",
            "signal": f"{context['specific_user']} completes {context['workflow_context']} repeatedly.",
            "expansion_motion": "Expand from the first team to adjacent teams using the same workflow.",
            "source_reference_ids": source_idea_ids,
        },
        {
            "id": "ET2",
            "trigger": "Buyer-visible value proof",
            "signal": f"{context['buyer']} can tie the pilot outcome to {context['value_proposition']}.",
            "expansion_motion": "Ask for renewal commitment and a scoped rollout plan.",
            "source_reference_ids": source_idea_ids,
        },
    ]
    if context["expansion_terms"]:
        triggers.append(
            {
                "id": "ET3",
                "trigger": "Expansion language appears in source context",
                "signal": f"Matched terms: {_inline_terms(context['expansion_terms'])}.",
                "expansion_motion": "Package the next account segment or integration as an expansion path.",
                "source_reference_ids": source_idea_ids,
            }
        )
    return triggers


def _expansion_opportunities(
    context: dict[str, Any],
    triggers: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    first_scope = context["mvp_scope"][0] if context["mvp_scope"] else context["workflow_context"]
    opportunities = [
        {
            "id": "EO1",
            "opportunity": "Team rollout",
            "confidence": "high" if context["readiness_band"] == "ready" else "medium",
            "why_it_matters": f"The first renewal case should show repeated value in {context['workflow_context']}.",
            "trigger": triggers[0]["trigger"],
            "proof_needed": "Activation and repeat-use evidence from the initial team.",
            "source_reference_ids": source_idea_ids,
        },
        {
            "id": "EO2",
            "opportunity": "Scope expansion",
            "confidence": "medium" if context["mvp_scope"] else "low",
            "why_it_matters": f"Next scope can build from {first_scope}.",
            "trigger": "Customer asks for adjacent capability or broader workflow coverage.",
            "proof_needed": "Usage evidence plus buyer-ranked backlog demand.",
            "source_reference_ids": source_idea_ids,
        },
    ]
    if context["first_customers"]:
        opportunities.append(
            {
                "id": "EO3",
                "opportunity": "Segment expansion",
                "confidence": "medium",
                "why_it_matters": f"Initial customer definition exists: {context['first_customers']}.",
                "trigger": "Two or more similar accounts show the same renewal value pattern.",
                "proof_needed": "Referenceable customer story and repeatable onboarding motion.",
                "source_reference_ids": source_idea_ids,
            }
        )
    return opportunities


def _customer_success_motions(
    context: dict[str, Any],
    renewal_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "CSM1",
            "motion": "Activation review",
            "owner_role": "Customer success owner",
            "cadence": "Within the first 14 days of launch",
            "success_evidence": f"Confirm {context['specific_user']} reaches first value in {context['workflow_context']}.",
        },
        {
            "id": "CSM2",
            "motion": "Value recap",
            "owner_role": "Product lead",
            "cadence": "Monthly through the first renewal cycle",
            "success_evidence": f"Document before/after value against {context['current_workaround']}.",
        },
        {
            "id": "CSM3",
            "motion": "Renewal risk review",
            "owner_role": "Account owner",
            "cadence": "At least 45 days before renewal or expansion ask",
            "success_evidence": f"Resolve or downgrade top risk: {renewal_risks[0]['risk']}.",
        },
    ]


def _proof_points(
    context: dict[str, Any],
    evidence_signals: list[dict[str, Any]],
    readiness_context: dict[str, Any],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    proof_points: list[dict[str, Any]] = []
    for signal in evidence_signals[:3]:
        proof_points.append(
            {
                "id": f"PP{len(proof_points) + 1}",
                "claim": signal["title"] or "Linked evidence signal",
                "strength": _proof_strength(signal.get("credibility", 0.0)),
                "evidence": signal["description"] or "Signal is linked but has no stored description.",
                "source_reference_ids": [signal["id"]],
            }
        )

    if readiness_context["strengths"]:
        proof_points.append(
            {
                "id": f"PP{len(proof_points) + 1}",
                "claim": "Readiness strengths support renewal planning",
                "strength": "medium",
                "evidence": readiness_context["strengths"][0],
                "source_reference_ids": source_idea_ids,
            }
        )

    if not proof_points:
        proof_points.append(
            {
                "id": "PP0",
                "claim": "Renewal proof is not yet captured",
                "strength": "missing",
                "evidence": context["validation_plan"],
                "source_reference_ids": source_idea_ids,
            }
        )
    return proof_points


def _next_actions(
    context: dict[str, Any],
    renewal_risks: list[dict[str, Any]],
    expansion_opportunities: list[dict[str, Any]],
    proof_points: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "id": "NA1",
            "owner_role": "Customer success owner",
            "action": f"Create the first-value checklist for {context['workflow_context']}.",
            "timing": "before pilot kickoff",
            "addresses": renewal_risks[0]["risk"],
        },
        {
            "id": "NA2",
            "owner_role": "Product lead",
            "action": f"Instrument renewal proof for {proof_points[0]['claim']}.",
            "timing": "during first active use",
            "addresses": "proof_points",
        },
        {
            "id": "NA3",
            "owner_role": "Account owner",
            "action": f"Pre-align {context['buyer']} on the expansion path: {expansion_opportunities[0]['opportunity']}.",
            "timing": "after first value recap",
            "addresses": expansion_opportunities[0]["id"],
        },
    ]


def _renewal_health(
    design_brief: dict[str, Any],
    renewal_risks: list[dict[str, Any]],
    proof_points: list[dict[str, Any]],
    missing_inputs: list[dict[str, Any]],
) -> str:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    high_risks = len([risk for risk in renewal_risks if risk["severity"] == "high"])
    proof_missing = any(proof["strength"] == "missing" for proof in proof_points)
    if missing_inputs or high_risks >= 2 or readiness < 45 or proof_missing:
        return "at_risk"
    if readiness >= 75 and high_risks == 0:
        return "healthy"
    return "watch"


def _readiness_band(readiness_score: float, status: str) -> str:
    if readiness_score >= 75 and status in _VALIDATED_STATUSES:
        return "ready"
    if readiness_score < 45 or status in _WEAK_STATUSES:
        return "early"
    return "partial"


def _proof_strength(credibility: float) -> str:
    if credibility >= 0.8:
        return "strong"
    if credibility > 0:
        return "medium"
    return "missing"


def _field_values(records: list[dict[str, Any]], field: str) -> list[str]:
    return [item for record in records for item in _string_list(record.get(field))]


def _first_with_fallback(
    fallbacks: list[str],
    label: str,
    *values: Any,
    fallback: str,
) -> str:
    value = _first_text(*values)
    if value:
        return value
    fallbacks.append(label)
    return fallback


def _first_text(*values: Any) -> str:
    for value in values:
        for item in _string_list(value):
            if item:
                return item
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    if isinstance(value, dict):
        return [str(item).strip() for item in value.values() if str(item).strip()]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_string_list(item))
        return items
    text = str(value).strip()
    return [text] if text else []


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in _string_list(values):
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _has_value(value: Any) -> bool:
    return bool(_string_list(value))


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "`none`"


def _inline_terms(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "design-brief"
