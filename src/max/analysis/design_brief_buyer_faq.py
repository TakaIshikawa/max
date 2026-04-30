"""Buyer-facing FAQ exports for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.analysis.design_brief_competitive_landscape import (
    build_design_brief_competitive_landscape,
)
from max.analysis.design_brief_evidence_matrix import build_design_brief_evidence_matrix
from max.analysis.design_brief_pricing_strategy import build_design_brief_pricing_strategy
from max.analysis.design_brief_risk_register import build_design_brief_risk_register
from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.buyer_faq.v1"

CONCERN_AREAS: tuple[tuple[str, str], ...] = (
    ("problem_fit", "Problem Fit"),
    ("differentiation", "Differentiation"),
    ("implementation_effort", "Implementation Effort"),
    ("security_compliance", "Security Or Compliance"),
    ("pricing", "Pricing"),
    ("adoption_risk", "Adoption Risk"),
    ("proof_points", "Proof Points"),
)


def build_design_brief_buyer_faq(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic buyer FAQ from a persisted design brief and supporting artifacts."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    pricing = build_design_brief_pricing_strategy(store, brief_id)
    competitive = build_design_brief_competitive_landscape(store, brief_id)
    risk_register = build_design_brief_risk_register(store, brief_id)
    evidence_matrix = build_design_brief_evidence_matrix(
        store,
        design_brief,
        generated_at=design_brief.get("updated_at") or design_brief.get("created_at"),
    )

    context = _context(design_brief, source_ideas)
    evidence_refs = _evidence_refs(pricing, evidence_matrix)
    risks = list((risk_register or {}).get("risks") or [])
    questions = _questions(
        design_brief,
        context,
        pricing,
        competitive,
        risks,
        evidence_matrix,
        evidence_refs,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.buyer_faq",
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
            "source_idea_ids": [idea["id"] for idea in source_ideas]
            or list(design_brief.get("source_idea_ids") or []),
        },
        "summary": {
            "buyer": context["buyer"],
            "specific_user": context["specific_user"],
            "workflow_context": context["workflow_context"],
            "question_count": len(questions),
            "evidence_ref_count": len(evidence_refs),
            "missing_input_count": len(_missing_inputs(pricing, competitive, evidence_matrix)),
        },
        "missing_inputs": _missing_inputs(pricing, competitive, evidence_matrix),
        "questions": questions,
        "concern_areas": [
            {
                "area": area,
                "title": title,
                "questions": [question for question in questions if question["area"] == area],
            }
            for area, title in CONCERN_AREAS
        ],
        "supporting_artifacts": {
            "pricing_strategy_schema": (pricing or {}).get("schema_version", ""),
            "competitive_landscape_schema": (competitive or {}).get("schema_version", ""),
            "risk_register_schema": (risk_register or {}).get("schema_version", ""),
            "evidence_matrix_schema": evidence_matrix.get("schema_version", ""),
        },
        "evidence_refs": evidence_refs,
    }


def render_design_brief_buyer_faq(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a buyer FAQ as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported buyer FAQ format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Buyer FAQ: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {summary['buyer']}",
        f"User: {summary['specific_user']}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
    ]
    if report["missing_inputs"]:
        lines.extend(["## Missing Inputs", ""])
        lines.extend(f"- `{item['input']}`: {item['reason']}" for item in report["missing_inputs"])
        lines.append("")

    for concern in report["concern_areas"]:
        lines.extend([f"## {concern['title']}", ""])
        for item in concern["questions"]:
            refs = ", ".join(f"`{ref['id']}`" for ref in item["evidence_refs"]) or "none"
            lines.extend(
                [
                    f"### {item['question']}",
                    "",
                    item["answer"],
                    "",
                    f"- Confidence: {item['confidence']:.2f}",
                    f"- Evidence refs: {refs}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _questions(
    design_brief: dict[str, Any],
    context: dict[str, str],
    pricing: dict[str, Any] | None,
    competitive: dict[str, Any] | None,
    risks: list[dict[str, Any]],
    evidence_matrix: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pricing_refs = evidence_refs[:5]
    problem_refs = _refs_for_claim(evidence_refs, evidence_matrix, "problem") or pricing_refs
    workflow_refs = _refs_for_claim(evidence_refs, evidence_matrix, "workflow") or pricing_refs
    risk_refs = _refs_for_claim(evidence_refs, evidence_matrix, "risks") or pricing_refs
    proof_refs = evidence_refs[:8]

    top_risk = risks[0]["description"] if risks else _first_text(_string_list(design_brief.get("risks")), "No explicit risk has been captured yet.")
    top_competitor = _top_competitor(competitive)
    package = ((pricing or {}).get("packages") or [{}])[1]
    band = ((pricing or {}).get("price_bands") or [{}])[1]
    pricing_confidence = float(((pricing or {}).get("confidence") or {}).get("score") or 0.35)
    competitive_confidence = 0.75 if (competitive or {}).get("status") == "ready" else 0.35
    evidence_confidence = _evidence_confidence(evidence_refs, evidence_matrix)
    risk_confidence = 0.7 if risks else 0.4

    items = [
        (
            "problem_fit",
            "FAQ1",
            f"What buyer problem does {design_brief['title']} solve?",
            (
                f"It helps {context['buyer']} support {context['specific_user']} in "
                f"{context['workflow_context']} by addressing: "
                f"{_first_text(design_brief.get('why_this_now'), design_brief.get('synthesis_rationale'), design_brief.get('merged_product_concept'))}."
            ),
            problem_refs,
            evidence_confidence,
        ),
        (
            "differentiation",
            "FAQ2",
            "How is this different from alternatives?",
            (
                f"The positioning is tied to the brief-specific workflow rather than generic feature parity. "
                f"{top_competitor}"
            ),
            proof_refs[:5],
            competitive_confidence,
        ),
        (
            "implementation_effort",
            "FAQ3",
            "What implementation effort should the buyer expect?",
            (
                f"The first implementation should focus on {_join_or_fallback(_string_list(design_brief.get('mvp_scope'))[:2], 'the core workflow')} "
                f"and start with {_join_or_fallback(_string_list(design_brief.get('first_milestones'))[:1], 'one validation milestone')}."
            ),
            workflow_refs,
            min(evidence_confidence + 0.1, 1.0),
        ),
        (
            "security_compliance",
            "FAQ4",
            "What security or compliance concerns should be discussed early?",
            (
                f"Start with the highest relevant risk: {top_risk} "
                "Confirm data handling, access control, and approval requirements before expanding a pilot."
            ),
            risk_refs,
            risk_confidence,
        ),
        (
            "pricing",
            "FAQ5",
            "How should the initial commercial offer be framed?",
            (
                f"Use the {package.get('name', 'Team')} package as the default paid pilot frame at "
                f"{_band_label(band)}. Anchor the offer to {((pricing or {}).get('value_metric') or {}).get('metric', 'measurable workflow value')}."
            ),
            pricing_refs,
            pricing_confidence,
        ),
        (
            "adoption_risk",
            "FAQ6",
            "What could slow adoption?",
            (
                f"The main adoption risk is {top_risk} "
                f"Use the validation plan to test commitment: {_first_text(design_brief.get('validation_plan'), 'Run buyer discovery before build-out')}."
            ),
            risk_refs,
            risk_confidence,
        ),
        (
            "proof_points",
            "FAQ7",
            "What proof points can sales or discovery teams cite?",
            (
                f"Use {len(proof_refs)} linked evidence reference(s), the readiness score "
                f"({float(design_brief.get('readiness_score') or 0.0):.1f}/100), and the validation plan as the current proof base."
            ),
            proof_refs,
            evidence_confidence,
        ),
    ]
    return [
        {
            "id": item_id,
            "area": area,
            "question": question,
            "answer": _sentence(answer),
            "evidence_refs": refs,
            "confidence": round(max(0.0, min(float(confidence), 1.0)), 2),
        }
        for area, item_id, question, answer, refs, confidence in items
    ]


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id = {
        source["idea_id"]: source
        for source in design_brief.get("sources", [])
        if source.get("idea_id")
    }
    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *list(design_brief.get("source_idea_ids") or []),
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
        ideas.append(data)
    return ideas


def _context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer"),
        "specific_user": _first_text(
            design_brief.get("specific_user"),
            _field_values(source_ideas, "specific_user"),
            "target user",
        ),
        "workflow_context": _first_text(
            design_brief.get("workflow_context"),
            _field_values(source_ideas, "workflow_context"),
            design_brief.get("merged_product_concept"),
            "the target workflow",
        ),
    }


def _evidence_refs(
    pricing: dict[str, Any] | None,
    evidence_matrix: dict[str, Any],
) -> list[dict[str, Any]]:
    refs_by_id: dict[str, dict[str, Any]] = {}
    for reference in (pricing or {}).get("evidence_references") or []:
        ref_id = str(reference.get("id") or "")
        if not ref_id:
            continue
        refs_by_id[ref_id] = {
            "id": ref_id,
            "type": "signal",
            "source_type": str(reference.get("source_type") or ""),
            "title": str(reference.get("title") or ref_id),
            "url": str(reference.get("url") or ""),
        }
    for row in evidence_matrix.get("rows", []):
        for source_id in row.get("supporting_source_idea_ids") or []:
            refs_by_id.setdefault(
                str(source_id),
                {
                    "id": str(source_id),
                    "type": "source_idea",
                    "source_type": "buildable_unit",
                    "title": str(source_id),
                    "url": "",
                },
            )
    return [refs_by_id[key] for key in sorted(refs_by_id)]


def _refs_for_claim(
    refs: list[dict[str, Any]],
    evidence_matrix: dict[str, Any],
    claim_area: str,
) -> list[dict[str, Any]]:
    row = next((item for item in evidence_matrix.get("rows", []) if item.get("claim_area") == claim_area), {})
    ids = set(row.get("supporting_signal_ids") or []) | set(row.get("supporting_source_idea_ids") or [])
    return [ref for ref in refs if ref["id"] in ids]


def _missing_inputs(
    pricing: dict[str, Any] | None,
    competitive: dict[str, Any] | None,
    evidence_matrix: dict[str, Any],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if not pricing or not pricing.get("evidence_references"):
        missing.append(
            {
                "input": "pricing_data",
                "reason": "No linked pricing, budget, survey, or market evidence references were found.",
            }
        )
    if not competitive or competitive.get("status") != "ready":
        missing.append(
            {
                "input": "competitive_data",
                "reason": "No stored prior-art records are linked to the design brief source ideas.",
            }
        )
    if not any(
        row.get("supporting_signal_ids") or row.get("supporting_insight_ids")
        for row in evidence_matrix.get("rows", [])
    ):
        missing.append(
            {
                "input": "evidence_data",
                "reason": "No linked signals or insights support the buyer-facing claims.",
            }
        )
    return missing


def _top_competitor(competitive: dict[str, Any] | None) -> str:
    clusters = (competitive or {}).get("competitor_clusters") or []
    for cluster in clusters:
        competitors = cluster.get("top_competitors") or []
        if competitors:
            return f"The closest stored alternative is {competitors[0].get('title', 'a prior-art match')}."
    positioning = (competitive or {}).get("recommended_positioning")
    if positioning:
        return str(positioning)
    return "Competitive evidence is not linked yet, so validate alternatives during discovery."


def _evidence_confidence(refs: list[dict[str, Any]], evidence_matrix: dict[str, Any]) -> float:
    strengths = [row.get("evidence_strength") for row in evidence_matrix.get("rows", [])]
    strong_count = sum(1 for strength in strengths if strength == "strong")
    moderate_count = sum(1 for strength in strengths if strength == "moderate")
    return round(min(0.35 + len(refs) * 0.08 + strong_count * 0.12 + moderate_count * 0.07, 0.95), 2)


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    return [_clean(item.get(field)) for item in items if _clean(item.get(field))]


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list | tuple):
            found = _first_text(*value)
            if found:
                return found
            continue
        clean = _clean(value)
        if clean:
            return clean
    return ""


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _join_or_fallback(items: list[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback


def _band_label(band: dict[str, Any]) -> str:
    low = band.get("monthly_min_usd")
    high = band.get("monthly_max_usd")
    if low is None or high is None:
        return "a discovery-priced pilot"
    return f"${low}-${high}/month"


def _sentence(value: str) -> str:
    clean = " ".join(str(value).split())
    if clean and clean[-1] not in ".!?":
        return clean + "."
    return clean
