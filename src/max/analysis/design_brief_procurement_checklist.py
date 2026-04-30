"""Deterministic procurement checklist export for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.procurement_checklist.v1"


SECTION_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "security_review",
        "title": "Security Review",
        "owner_role": "Security owner",
        "description": "Confirm the product can pass buyer security review and technical due diligence.",
        "source_fields": ["tech_approach", "suggested_stack", "risks", "domain_risks"],
    },
    {
        "id": "legal_privacy",
        "title": "Legal / Privacy",
        "owner_role": "Legal or privacy owner",
        "description": "Confirm personal data, contractual, compliance, and policy assumptions before vendor review.",
        "source_fields": ["workflow_context", "specific_user", "buyer", "risks", "domain_risks"],
    },
    {
        "id": "budget_owner",
        "title": "Budget Owner",
        "owner_role": "Commercial owner",
        "description": "Identify who owns spend, value proof, pricing assumptions, and approval authority.",
        "source_fields": ["buyer", "value_proposition", "first_10_customers", "evidence_rationale"],
    },
    {
        "id": "vendor_evaluation",
        "title": "Vendor Evaluation",
        "owner_role": "Procurement owner",
        "description": "Prepare vendor comparison, buying criteria, and procurement package inputs.",
        "source_fields": ["problem", "solution", "current_workaround", "merged_product_concept"],
    },
    {
        "id": "implementation_owner",
        "title": "Implementation Owner",
        "owner_role": "Implementation owner",
        "description": "Confirm rollout ownership, support coverage, and operational handoff evidence.",
        "source_fields": ["specific_user", "workflow_context", "mvp_scope", "first_milestones", "validation_plan"],
    },
    {
        "id": "approval_gates",
        "title": "Approval Gates",
        "owner_role": "Product lead",
        "description": "Sequence approvals needed before a buyer can adopt or expand the product.",
        "source_fields": ["design_status", "readiness_score", "validation_plan", "risks"],
    },
)

REQUIRED_INPUTS: tuple[dict[str, str], ...] = (
    {
        "field": "buyer",
        "label": "Buyer or budget sponsor",
        "fallback": "Use the named product owner as the temporary procurement sponsor.",
    },
    {
        "field": "risks",
        "label": "Procurement, security, legal, or delivery risks",
        "fallback": "Add a fallback risk review item for security, legal, and implementation owners.",
    },
    {
        "field": "pricing_strategy",
        "label": "Pricing strategy or value metric",
        "fallback": "Validate budget range and value metric before buyer review.",
    },
    {
        "field": "market_sizing_hints",
        "label": "Market sizing or customer segment evidence",
        "fallback": "Use source evidence and first-customer notes as market sizing placeholders.",
    },
    {
        "field": "support_needs",
        "label": "Support needs and operational ownership",
        "fallback": "Assign support owner and escalation path before procurement handoff.",
    },
    {
        "field": "validation_plan",
        "label": "Validation plan",
        "fallback": "Require a validation plan before approval to buy or expand.",
    },
)


def build_design_brief_procurement_checklist(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a procurement readiness checklist from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _procurement_context(design_brief, source_ideas)
    missing_inputs = _missing_inputs(context)
    sections = _sections(design_brief, source_ideas, source_idea_ids, context)
    checklist_items = _flatten_items(sections)
    approval_gates = _approval_gates(design_brief, context, missing_inputs)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.procurement_checklist",
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
            "procurement_gate": _procurement_gate(design_brief, missing_inputs),
            "section_count": len(sections),
            "item_count": len(checklist_items),
            "approval_gate_count": len(approval_gates),
            "missing_input_count": len(missing_inputs),
            "source_idea_count": len(source_idea_ids),
        },
        "procurement_context": context,
        "sections": sections,
        "checklist_items": checklist_items,
        "approval_gates": approval_gates,
        "missing_inputs": missing_inputs,
        "recommended_next_actions": _recommended_next_actions(design_brief, missing_inputs),
        "source_ideas": source_ideas,
    }


def render_design_brief_procurement_checklist(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a procurement checklist as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported procurement checklist format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Procurement Checklist: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Workflow: {brief['workflow_context']}",
        f"Procurement gate: {summary['procurement_gate']}",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
    ]

    for section in report["sections"]:
        lines.extend([f"## {section['title']}", "", section["description"], ""])
        lines.extend(
            [
                f"- Owner role: {section['owner_role']}",
                f"- Source fields: {', '.join(section['source_fields'])}",
                "",
            ]
        )
        for item in section["items"]:
            lines.extend(
                [
                    f"### {item['id']}: {item['task']}",
                    "",
                    f"- Owner role: {item['owner_role']}",
                    f"- Rationale: {item['rationale']}",
                    f"- Source fields: {', '.join(item['source_fields'])}",
                    f"- Completion evidence: {item['completion_evidence']}",
                    f"- Status: {item['status']}",
                    "",
                ]
            )

    lines.extend(["## Approval Gates", ""])
    for gate in report["approval_gates"]:
        lines.extend(
            [
                f"- **{gate['name']}** ({gate['owner_role']}): {gate['criteria']}",
                f"  Evidence: {gate['completion_evidence']}",
            ]
        )

    lines.extend(["", "## Missing Inputs", ""])
    if report["missing_inputs"]:
        for missing in report["missing_inputs"]:
            lines.append(f"- **{missing['field']}**: {missing['warning']} Fallback: {missing['fallback']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {action}" for action in report["recommended_next_actions"])
    return "\n".join(lines).rstrip() + "\n"


def procurement_checklist_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-procurement-checklist.{extension}"
    )


def _procurement_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "TBD buyer")
    specific_user = _first_text(
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        _field_values(source_ideas, "target_users"),
        "target user",
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        f"{design_brief['title']} adoption workflow",
    )
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    pricing = _pricing_strategy(design_brief, source_ideas)
    market = _market_sizing_hints(source_ideas)
    support = _support_needs(design_brief, source_ideas, risks)
    compliance = _compliance_notes(risks, source_ideas)
    validation = _first_text(
        design_brief.get("validation_plan"),
        _field_values(source_ideas, "validation_plan"),
    )

    return {
        "buyer": buyer,
        "specific_user": specific_user,
        "workflow_context": workflow,
        "risks": risks,
        "compliance_notes": compliance,
        "pricing_strategy": pricing,
        "market_sizing_hints": market,
        "support_needs": support,
        "validation_plan": validation,
    }


def _sections(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    item_number = 1
    for config in SECTION_CONFIGS:
        raw_items = _section_items(config["id"], design_brief, source_ideas, source_idea_ids, context)
        items = []
        for raw in raw_items:
            items.append({"id": f"DBPC{item_number}", "status": "pending", **raw})
            item_number += 1
        sections.append(
            {
                "id": config["id"],
                "title": config["title"],
                "description": config["description"],
                "owner_role": config["owner_role"],
                "source_fields": config["source_fields"],
                "items": items,
            }
        )
    return sections


def _section_items(
    section_id: str,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    if section_id == "security_review":
        return [
            _item(
                task="Prepare security questionnaire inputs for architecture, access, and data boundaries.",
                owner_role="Security owner",
                rationale=_first_text(
                    _joined_fields(source_ideas, ("tech_approach", "suggested_stack")),
                    design_brief.get("merged_product_concept"),
                    "Security architecture is not yet explicit.",
                ),
                source_fields=["tech_approach", "suggested_stack", "merged_product_concept"],
                completion_evidence="Completed security questionnaire notes or not-applicable decision.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("tech_approach", "suggested_stack"), source_idea_ids),
            ),
            _item(
                task="Assign mitigation owners for buyer-visible security risks.",
                owner_role="Security owner",
                rationale="; ".join(context["risks"]) or "No security risks are captured yet.",
                source_fields=["risks", "domain_risks", "compliance_notes"],
                completion_evidence="Risk register entries include owner, mitigation, and buyer disclosure decision.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("domain_risks", "evidence_rationale"), source_idea_ids),
            ),
        ]
    if section_id == "legal_privacy":
        return [
            _item(
                task="Document data, privacy, and contractual assumptions for the buyer workflow.",
                owner_role="Legal or privacy owner",
                rationale=context["compliance_notes"] or "Legal and privacy assumptions are not yet documented.",
                source_fields=["workflow_context", "specific_user", "buyer", "domain_risks"],
                completion_evidence="Privacy notes identify data categories, processing purpose, and contract needs.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("workflow_context", "specific_user", "buyer"), source_idea_ids),
            ),
            _item(
                task="Decide whether legal review is required before procurement handoff.",
                owner_role="Legal or privacy owner",
                rationale="Procurement packages need a clear legal review, waive, or defer decision.",
                source_fields=["risks", "domain_risks", "validation_plan"],
                completion_evidence="Legal review decision is recorded with accountable owner and date.",
                source_idea_ids=source_idea_ids,
            ),
        ]
    if section_id == "budget_owner":
        return [
            _item(
                task="Name the budget owner and economic buyer for the first procurement conversation.",
                owner_role="Commercial owner",
                rationale=f"Current buyer signal: {context['buyer']}.",
                source_fields=["buyer", "first_10_customers"],
                completion_evidence="Budget owner, signer, and evaluator roles are named.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("buyer", "first_10_customers"), source_idea_ids),
            ),
            _item(
                task="Validate price, value metric, and budget range before buyer review.",
                owner_role="Commercial owner",
                rationale=context["pricing_strategy"],
                source_fields=["value_proposition", "evidence_rationale", "pricing_strategy"],
                completion_evidence="Pricing notes include value metric, expected package, and budget objection response.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("value_proposition", "evidence_rationale"), source_idea_ids),
            ),
        ]
    if section_id == "vendor_evaluation":
        return [
            _item(
                task="Write vendor evaluation criteria tied to the buyer problem and current workaround.",
                owner_role="Procurement owner",
                rationale=_first_text(
                    design_brief.get("merged_product_concept"),
                    _joined_fields(source_ideas, ("problem", "solution")),
                    "The vendor evaluation narrative needs a problem and solution anchor.",
                ),
                source_fields=["problem", "solution", "current_workaround", "merged_product_concept"],
                completion_evidence="Evaluation criteria compare problem fit, replacement path, and procurement risk.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("problem", "solution", "current_workaround"), source_idea_ids),
            ),
            _item(
                task="Attach market sizing and customer segment evidence to the procurement package.",
                owner_role="Procurement owner",
                rationale=context["market_sizing_hints"],
                source_fields=["first_10_customers", "evidence_signals", "inspiring_insights", "market_sizing_hints"],
                completion_evidence="Procurement packet includes target segment, evidence links, and confidence notes.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("first_10_customers", "evidence_signals", "inspiring_insights"), source_idea_ids),
            ),
        ]
    if section_id == "implementation_owner":
        return [
            _item(
                task="Assign implementation owner for rollout, onboarding, and success measurement.",
                owner_role="Implementation owner",
                rationale=f"Workflow to support: {context['workflow_context']}.",
                source_fields=["specific_user", "workflow_context", "first_milestones"],
                completion_evidence="Implementation owner and onboarding responsibilities are recorded.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("specific_user", "workflow_context"), source_idea_ids),
            ),
            _item(
                task="Define support needs, escalation path, and validation evidence for adoption.",
                owner_role="Implementation owner",
                rationale=context["support_needs"],
                source_fields=["validation_plan", "mvp_scope", "domain_risks", "support_needs"],
                completion_evidence="Support plan names channel, escalation owner, and validation evidence to capture.",
                source_idea_ids=source_idea_ids,
            ),
        ]
    return [
        _item(
            task="Sequence security, legal, budget, vendor, and implementation approvals.",
            owner_role="Product lead",
            rationale="Procurement readiness requires explicit gate order and accountable approvers.",
            source_fields=["design_status", "readiness_score", "risks"],
            completion_evidence="Approval gate checklist has owner, criteria, status, and blocker handling.",
            source_idea_ids=source_idea_ids,
        ),
        _item(
            task="Block expansion until missing procurement inputs are resolved or explicitly accepted.",
            owner_role="Product lead",
            rationale="Missing inputs should be visible before buyer-facing commitments are made.",
            source_fields=["validation_plan", "buyer", "pricing_strategy", "market_sizing_hints"],
            completion_evidence="Missing inputs are resolved, accepted, or converted into dated follow-up work.",
            source_idea_ids=source_idea_ids,
        ),
    ]


def _item(
    *,
    task: str,
    owner_role: str,
    rationale: str,
    source_fields: list[str],
    completion_evidence: str,
    source_idea_ids: list[str],
) -> dict[str, Any]:
    return {
        "task": task,
        "owner_role": owner_role,
        "rationale": _compact(rationale),
        "source_fields": source_fields,
        "completion_evidence": completion_evidence,
        "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
    }


def _approval_gates(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    missing_inputs: list[dict[str, str]],
) -> list[dict[str, str]]:
    gates = [
        (
            "Security review",
            "Security owner",
            "Architecture, access boundaries, and buyer-visible security risks are accepted.",
            "Security questionnaire or risk acceptance record.",
        ),
        (
            "Legal / privacy review",
            "Legal or privacy owner",
            "Data, privacy, contractual, and compliance assumptions are accepted or waived.",
            "Legal or privacy review decision.",
        ),
        (
            "Budget approval",
            "Commercial owner",
            f"{context['buyer']} confirms budget ownership, value metric, and buying path.",
            "Budget owner confirmation and pricing notes.",
        ),
        (
            "Implementation approval",
            "Implementation owner",
            "Implementation owner accepts rollout, support, and validation responsibilities.",
            "Implementation handoff and support plan.",
        ),
    ]
    if missing_inputs:
        gates.append(
            (
                "Missing input resolution",
                "Product lead",
                f"{len(missing_inputs)} missing procurement input(s) are resolved or accepted.",
                "Missing input decision log.",
            )
        )
    if design_brief.get("design_status") not in {"approved", "published"}:
        gates.insert(
            0,
            (
                "Design approval",
                "Product lead",
                "Design brief is approved before procurement materials are used externally.",
                "Approved design brief status.",
            ),
        )
    return [
        {
            "id": f"gate-{index}",
            "name": name,
            "owner_role": owner_role,
            "criteria": criteria,
            "completion_evidence": evidence,
        }
        for index, (name, owner_role, criteria, evidence) in enumerate(gates, start=1)
    ]


def _missing_inputs(context: dict[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for item in REQUIRED_INPUTS:
        field = item["field"]
        value = context.get(field)
        is_missing = not value or value == "TBD buyer"
        if isinstance(value, list):
            is_missing = not value
        if is_missing:
            missing.append(
                {
                    "field": field,
                    "label": item["label"],
                    "warning": f"{item['label']} is not available from the persisted brief lineage.",
                    "fallback": item["fallback"],
                }
            )
    return missing


def _recommended_next_actions(
    design_brief: dict[str, Any],
    missing_inputs: list[dict[str, str]],
) -> list[str]:
    actions = [
        "Review every procurement section with the named owner before buyer-facing handoff.",
        "Attach completion evidence for security, legal, budget, vendor, implementation, and approval gate items.",
        "Use the validation plan to test budget authority and procurement objections before expansion.",
    ]
    if design_brief.get("design_status") not in {"approved", "published"}:
        actions.insert(0, "Approve the design brief before treating this checklist as procurement-ready.")
    if missing_inputs:
        fields = ", ".join(item["field"] for item in missing_inputs)
        actions.insert(0, f"Resolve or explicitly accept missing procurement inputs: {fields}.")
    return actions


def _procurement_gate(design_brief: dict[str, Any], missing_inputs: list[dict[str, str]]) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if missing_inputs:
        return "needs_procurement_inputs"
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_procurement_review"
    if status in {"approved", "published"}:
        return "approved_needs_procurement_readiness"
    return "needs_design_approval"


def _pricing_strategy(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> str:
    values = [
        design_brief.get("value_proposition"),
        _joined_fields(source_ideas, ("value_proposition", "evidence_rationale")),
    ]
    text = _first_text(*values)
    if not text:
        return ""
    return f"Anchor pricing to value proof: {text}"


def _market_sizing_hints(source_ideas: list[dict[str, Any]]) -> str:
    first_customers = _joined_fields(source_ideas, ("first_10_customers",))
    evidence = _source_evidence_ids(source_ideas)
    if first_customers and evidence:
        return f"Initial segment: {first_customers}. Evidence: {', '.join(evidence)}."
    if first_customers:
        return f"Initial segment: {first_customers}."
    if evidence:
        return f"Linked market evidence: {', '.join(evidence)}."
    return ""


def _support_needs(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    risks: list[str],
) -> str:
    validation = _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan"))
    workflow = _first_text(design_brief.get("workflow_context"), _field_values(source_ideas, "workflow_context"))
    if validation and workflow:
        return f"Support {workflow} while capturing validation evidence: {validation}"
    if validation:
        return f"Support validation evidence capture: {validation}"
    if risks:
        return f"Support plan should cover top procurement risk: {risks[0]}"
    return ""


def _compliance_notes(risks: list[str], source_ideas: list[dict[str, Any]]) -> str:
    notes = [
        risk
        for risk in risks
        if _contains_any(risk, ("compliance", "privacy", "legal", "security", "data", "audit"))
    ]
    notes.extend(
        value
        for value in _field_values(source_ideas, "evidence_rationale")
        if _contains_any(value, ("compliance", "privacy", "legal", "security", "data", "audit"))
    )
    return "; ".join(_dedupe(notes))


def _flatten_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "section_id": section["id"],
            "section_title": section["title"],
            "section_owner_role": section["owner_role"],
        }
        for section in sections
        for item in section["items"]
    ]


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


def _source_ids_for_fields(
    source_ideas: list[dict[str, Any]],
    fields: tuple[str, ...],
    fallback: list[str],
) -> list[str]:
    ids = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and any(_has_value(idea.get(field)) for field in fields)
    ]
    return list(dict.fromkeys(ids)) or fallback


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _joined_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        values.extend(_field_values(source_ideas, field))
    return "; ".join(_dedupe(values))


def _source_evidence_ids(source_ideas: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        values.extend(_string_list(idea.get("evidence_signals")))
        values.extend(_string_list(idea.get("inspiring_insights")))
    return sorted(_dedupe(values))


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(needle in lowered for needle in needles)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, dict):
        return [_compact(f"{key}: {item}") for key, item in value.items() if _compact(key)]
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _compact("; ".join(value))
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
