"""Deterministic onboarding plans for approved design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.onboarding_plan.v1"


def build_design_brief_onboarding_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a customer onboarding plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _onboarding_context(design_brief, lead_idea, source_ideas)
    evidence_references = _evidence_references(source_ideas)
    risks = _onboarding_risks(design_brief, source_ideas, source_idea_ids)
    phases = _onboarding_phases(design_brief, context, evidence_references, risks, source_idea_ids)
    success_criteria = _success_criteria(design_brief, context, evidence_references)
    required_assets = _required_assets(design_brief, context, risks, source_idea_ids)
    owner_hints = _owner_hints(context, risks)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.onboarding_plan",
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
        },
        "summary": {
            "onboarding_goal": f"Turn pilot approval for {design_brief['title']} into repeatable customer activation.",
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "phase_count": len(phases),
            "success_criteria_count": len(success_criteria),
            "risk_count": len(risks),
            "required_asset_count": len(required_assets),
            "evidence_reference_count": len(evidence_references),
        },
        "onboarding_phases": phases,
        "success_criteria": success_criteria,
        "owner_hints": owner_hints,
        "risks": risks,
        "required_assets": required_assets,
        "evidence_references": evidence_references,
        "source_ideas": source_ideas,
    }


def render_design_brief_onboarding_plan(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render an onboarding plan as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported onboarding plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Onboarding Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Onboarding Summary",
        "",
        f"- Goal: {summary['onboarding_goal']}",
        f"- Target user: {summary['target_user']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        "",
        "## Onboarding Phases",
        "",
    ]
    for phase in report["onboarding_phases"]:
        lines.extend(
            [
                f"### {phase['id']}: {phase['name']}",
                "",
                f"- Owner: {phase['owner']}",
                f"- Goal: {phase['goal']}",
                f"- Actions: {_inline_list(phase['actions'])}",
                f"- Exit criteria: {phase['exit_criteria']}",
                f"- Evidence references: {_inline_ids(phase['evidence_reference_ids'])}",
                "",
            ]
        )

    lines.extend(["## Success Criteria", ""])
    for criterion in report["success_criteria"]:
        lines.extend(
            [
                f"- **{criterion['metric']}**: {criterion['target']}",
                f"  Evidence: {criterion['evidence']}",
            ]
        )

    lines.extend(["", "## Owner Hints", ""])
    for hint in report["owner_hints"]:
        lines.extend(
            [
                f"- **{hint['owner']}**: {hint['responsibility']}",
                f"  Handoff: {hint['handoff_signal']}",
            ]
        )

    lines.extend(["", "## Risks", ""])
    for risk in report["risks"]:
        lines.extend(
            [
                f"- **{risk['id']} {risk['name']}**: {risk['risk']}",
                f"  Mitigation: {risk['mitigation']}",
            ]
        )

    lines.extend(["", "## Required Assets", ""])
    for asset in report["required_assets"]:
        lines.extend(
            [
                f"- **{asset['name']}** ({asset['owner']}): {asset['purpose']}",
                f"  Ready when: {asset['ready_when']}",
            ]
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for reference in report["evidence_references"]:
            lines.append(
                f"- **{reference['id']}** ({reference['source_idea_id']}): {reference['description']}"
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _onboarding_context(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
    source_ideas: list[dict[str, Any]],
) -> dict[str, str]:
    title = str(design_brief["title"])
    target_user = _first_text(
        design_brief.get("specific_user"),
        lead_idea and lead_idea.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        f"{title} user",
    )
    buyer = _first_text(
        design_brief.get("buyer"),
        lead_idea and lead_idea.get("buyer"),
        _field_values(source_ideas, "buyer"),
        "customer sponsor",
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        f"{title} workflow",
    )
    current_workaround = _first_text(
        lead_idea and lead_idea.get("current_workaround"),
        _field_values(source_ideas, "current_workaround"),
        "the current customer process",
    )
    value = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("value_proposition"),
        f"Help {target_user} complete {workflow}.",
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    validation = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Confirm customers can reach first value and continue without concierge support.",
    )
    return {
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "current_workaround": current_workaround,
        "value_proposition": value,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "first_milestone": milestones[0] if milestones else "first customer-ready workflow",
        "validation_plan": validation,
    }


def _onboarding_phases(
    design_brief: dict[str, Any],
    context: dict[str, str],
    evidence_references: list[dict[str, str]],
    risks: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    evidence_ids = [reference["id"] for reference in evidence_references]
    risk_text = risks[0]["risk"] if risks else "No explicit onboarding risk captured."
    return [
        {
            "id": "phase-1",
            "name": "Account Readiness",
            "owner": "Customer success lead",
            "goal": f"Confirm {context['buyer']} and {context['target_user']} are ready to start {context['workflow_context']}.",
            "actions": [
                "Confirm sponsor, participating users, kickoff date, and success definition.",
                f"Map the customer's current workaround: {context['current_workaround']}.",
                f"Review scope boundary for {context['primary_scope']}.",
            ],
            "exit_criteria": "Sponsor, users, baseline workflow, and first-value target are recorded before setup starts.",
            "evidence_reference_ids": evidence_ids,
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "phase-2",
            "name": "Guided First Value",
            "owner": "Onboarding specialist",
            "goal": f"Guide the first {context['target_user']} through {context['first_milestone']} with support coverage.",
            "actions": [
                "Run setup with the customer and capture friction in the onboarding log.",
                f"Observe the first attempt at {context['workflow_context']}.",
                "Record activation, blocker, and support-request evidence before closing the session.",
            ],
            "exit_criteria": "At least one customer user reaches first value or the blocker is assigned with a recovery date.",
            "evidence_reference_ids": evidence_ids,
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "phase-3",
            "name": "Team Enablement",
            "owner": "Product enablement owner",
            "goal": "Turn the guided path into repeatable materials for the remaining customer users.",
            "actions": [
                "Publish quickstart, FAQ, support path, and admin checklist.",
                "Train sponsor or champion on common setup and scope questions.",
                f"Validate the plan against known risk: {risk_text}",
            ],
            "exit_criteria": "Customer champion can onboard the next user with no unowned blocker or scope ambiguity.",
            "evidence_reference_ids": evidence_ids,
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "phase-4",
            "name": "Adoption Handoff",
            "owner": "Customer owner",
            "goal": "Move from onboarding to steady-state adoption, support monitoring, and expansion decisioning.",
            "actions": [
                "Review success criteria with sponsor and customer users.",
                "Assign owners for unresolved risks, requested changes, and expansion candidates.",
                "Create the adoption review cadence and handoff notes for support and product.",
            ],
            "exit_criteria": "Sponsor accepts the adoption plan, support path, and next review date.",
            "evidence_reference_ids": evidence_ids,
            "source_idea_ids": source_idea_ids,
        },
    ]


def _success_criteria(
    design_brief: dict[str, Any],
    context: dict[str, str],
    evidence_references: list[dict[str, str]],
) -> list[dict[str, str]]:
    evidence_count = len(evidence_references)
    return [
        {
            "metric": "First value reached",
            "target": f"At least one {context['target_user']} completes {context['workflow_context']} during guided onboarding.",
            "evidence": "Onboarding log, usage event, or customer-confirmed completion note.",
        },
        {
            "metric": "Repeatable enablement",
            "target": "Customer champion can repeat setup or invite the next user without unscheduled product-team help.",
            "evidence": "Champion walkthrough notes, support transcript, or enablement checklist sign-off.",
        },
        {
            "metric": "Sponsor acceptance",
            "target": f"{context['buyer']} agrees the onboarding outcome supports the approved pilot value proposition.",
            "evidence": "Sponsor closeout note, adoption review, or renewal/expansion signal.",
        },
        {
            "metric": "Evidence continuity",
            "target": f"Onboarding adds customer evidence to the {evidence_count} linked source evidence reference(s).",
            "evidence": _first_text(
                design_brief.get("validation_plan"),
                context["validation_plan"],
            ),
        },
    ]


def _owner_hints(context: dict[str, str], risks: list[dict[str, Any]]) -> list[dict[str, str]]:
    risk = risks[0]["risk"] if risks else "Watch for onboarding friction that delays first value."
    return [
        {
            "owner": "Customer success lead",
            "responsibility": "Own sponsor alignment, kickoff readiness, and account-level adoption status.",
            "handoff_signal": f"{context['buyer']} accepts the onboarding scope and success definition.",
        },
        {
            "owner": "Onboarding specialist",
            "responsibility": "Own guided setup, first-value session notes, and blocker recovery.",
            "handoff_signal": f"{context['target_user']} completes the first workflow attempt or has a dated recovery plan.",
        },
        {
            "owner": "Product lead",
            "responsibility": "Own scope decisions, success criteria changes, and product feedback routing.",
            "handoff_signal": f"Feedback is classified against {context['primary_scope']} and routed to roadmap or support.",
        },
        {
            "owner": "Risk owner",
            "responsibility": risk,
            "handoff_signal": "Mitigation, customer impact, and expansion disposition are recorded before adoption handoff.",
        },
    ]


def _onboarding_risks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    raw_risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_source_risks(source_ideas)]
    )
    if not raw_risks:
        raw_risks = ["Customer reaches setup but does not repeat the workflow without guided help."]
    risks: list[dict[str, Any]] = []
    for index, risk in enumerate(raw_risks[:4], start=1):
        risks.append(
            {
                "id": f"R{index}",
                "name": _risk_name(risk, index),
                "risk": risk,
                "impact": _risk_impact(risk),
                "mitigation": _risk_mitigation(risk),
                "owner": "Risk owner" if index == 1 else "Product lead",
                "source_idea_ids": source_idea_ids,
            }
        )
    return risks


def _required_assets(
    design_brief: dict[str, Any],
    context: dict[str, str],
    risks: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    risk = risks[0]["risk"] if risks else "onboarding risk"
    return [
        {
            "id": "A1",
            "name": "Kickoff agenda",
            "owner": "Customer success lead",
            "purpose": f"Align {context['buyer']} and {context['target_user']} on workflow, roles, and success criteria.",
            "ready_when": "Agenda includes participants, baseline workflow, data boundaries, and first-value target.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "A2",
            "name": "Setup checklist",
            "owner": "Onboarding specialist",
            "purpose": f"Prepare the customer to complete {context['workflow_context']} with minimal manual recovery.",
            "ready_when": f"Checklist covers prerequisites, access, sample data, and {context['primary_scope']}.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "A3",
            "name": "Enablement guide",
            "owner": "Product enablement owner",
            "purpose": "Help the customer champion onboard additional users after the guided session.",
            "ready_when": "Guide includes quickstart steps, FAQ, supported scope, and support escalation path.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "A4",
            "name": "Adoption review template",
            "owner": "Customer owner",
            "purpose": "Record success criteria, unresolved risks, and the next adoption or expansion decision.",
            "ready_when": f"Template includes validation plan, linked evidence, and mitigation status for: {risk}",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _evidence_references(source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for field in ("evidence_signals", "inspiring_insights"):
            for value in _string_list(idea.get(field)):
                key = (str(idea["id"]), _compact(value).lower())
                if key in seen:
                    continue
                seen.add(key)
                prefix = "sig" if field == "evidence_signals" else "ins"
                references.append(
                    {
                        "id": f"{prefix}-{_slug(str(idea['id']))}-{len(references) + 1}",
                        "source_idea_id": str(idea["id"]),
                        "field": field,
                        "description": value,
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


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _risk_name(risk: str, index: int) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in ("privacy", "security", "data", "compliance")):
        return "Data or trust blocker"
    if any(term in lowered for term in ("adoption", "repeat", "change", "workflow")):
        return "Adoption friction"
    if any(term in lowered for term in ("support", "setup", "training")):
        return "Enablement gap"
    return f"Onboarding risk {index}"


def _risk_impact(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in ("privacy", "security", "data", "compliance")):
        return "Customer onboarding or expansion may pause until trust requirements are resolved."
    if any(term in lowered for term in ("adoption", "repeat", "workflow")):
        return "Customers may need repeated concierge support instead of self-service adoption."
    return "The customer may not reach first value or may defer broader rollout."


def _risk_mitigation(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in ("privacy", "security", "data", "compliance")):
        return "Confirm data boundaries, approvals, and customer-facing trust notes before setup."
    if any(term in lowered for term in ("adoption", "repeat", "workflow")):
        return "Add champion enablement, usage review, and recovery actions before adoption handoff."
    return "Assign an owner, capture the trigger, and review mitigation at every phase exit."


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [str(idea.get(field) or "") for idea in source_ideas if not idea.get("missing")]


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _inline_list(values: list[str]) -> str:
    return "; ".join(values) if values else "none"


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
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = _compact(value)
        key = re.sub(r"\s+", " ", text.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "source"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
