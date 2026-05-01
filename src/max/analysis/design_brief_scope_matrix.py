"""Deterministic MoSCoW scope matrices for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.scope_matrix"
SCHEMA_VERSION = "max.design_brief.scope_matrix.v1"

_BUCKETS: tuple[tuple[str, str], ...] = (
    ("must_have", "Must Have"),
    ("should_have", "Should Have"),
    ("could_have", "Could Have"),
    ("wont_have_now", "Won't Have Now"),
)

_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("specific_user", "Specific user is needed to decide what belongs in the first workflow."),
    ("buyer", "Buyer is needed to separate must-have outcomes from nice-to-have polish."),
    ("workflow_context", "Workflow context is needed to draw a concrete scope boundary."),
    ("merged_product_concept", "Merged product concept is needed to anchor the scope decision."),
    ("mvp_scope", "MVP scope is needed to form must-have implementation boundaries."),
    ("validation_plan", "Validation plan is needed to decide what should be built before launch."),
    ("risks", "Risks are needed to identify explicit won't-have-now guardrails."),
    ("source_idea_ids", "Source ideas are needed for traceable evidence references."),
)


def build_design_brief_scope_matrix(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic MoSCoW scope decision matrix from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    evidence_refs = _evidence_references(store, source_ideas)
    evidence_ids = [reference["id"] for reference in evidence_refs]
    context = _scope_context(design_brief, source_ideas)
    missing_inputs = _missing_inputs(design_brief, source_ideas)
    buckets = _scope_buckets(context, evidence_ids, source_idea_ids, bool(missing_inputs))
    items = [item for bucket, _label in _BUCKETS for item in buckets[bucket]]

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
            "bucket_count": len(_BUCKETS),
            "item_count": len(items),
            "must_have_count": len(buckets["must_have"]),
            "should_have_count": len(buckets["should_have"]),
            "could_have_count": len(buckets["could_have"]),
            "wont_have_now_count": len(buckets["wont_have_now"]),
            "confidence": _overall_confidence(items, missing_inputs),
            "primary_scope_boundary": buckets["must_have"][0]["decision"],
        },
        "scope_context": context,
        "buckets": buckets,
        "items": items,
        "missing_inputs": missing_inputs,
        "evidence_refs": evidence_refs,
        "source_ideas": source_ideas,
    }


def render_design_brief_scope_matrix(matrix: dict[str, Any], fmt: str = "json") -> str:
    """Render a scope decision matrix as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(matrix, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported scope matrix format: {fmt}")

    brief = matrix["design_brief"]
    lines = [
        f"# Scope Decision Matrix: {brief['title']}",
        "",
        f"Schema: `{matrix['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Confidence: {matrix['summary']['confidence']}",
        "",
    ]

    for bucket, label in _BUCKETS:
        lines.extend([f"## {label}", ""])
        entries = matrix["buckets"].get(bucket, [])
        if not entries:
            lines.extend(["- None", ""])
            continue
        for item in entries:
            lines.extend(
                [
                    f"### {item['id']}: {item['decision']}",
                    "",
                    f"- **Confidence**: {item['confidence']}",
                    f"- **Rationale**: {item['rationale']}",
                    f"- **Dependencies**: {_inline_list(item['dependencies'])}",
                    f"- **Evidence refs**: {_inline_ids(item['evidence_refs'])}",
                    "",
                ]
            )

    lines.extend(["## Missing Inputs", ""])
    if matrix["missing_inputs"]:
        lines.extend(f"- **{item['field']}**: {item['reason']}" for item in matrix["missing_inputs"])
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def scope_matrix_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a scope matrix export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    return f"{brief_id}-scope-matrix.{extension}"


def _scope_buckets(
    context: dict[str, Any],
    evidence_ids: list[str],
    source_idea_ids: list[str],
    has_missing_inputs: bool,
) -> dict[str, list[dict[str, Any]]]:
    readiness = float(context["readiness_score"] or 0.0)
    sparse = has_missing_inputs
    must_decision = (
        f"Deliver the narrow {context['workflow_context']} workflow for {context['specific_user']}."
        if not sparse
        else "Complete the missing scope inputs before committing implementation work."
    )
    should_decision = (
        f"Package validation and first milestone support for {context['buyer']} review."
        if not sparse
        else "Keep validation support provisional until buyer, user, workflow, and risks are explicit."
    )
    could_decision = (
        f"Add secondary source-idea enhancements after the core workflow is validated."
        if source_idea_ids and not sparse
        else "Defer optional enhancements until source evidence and MVP boundaries are complete."
    )
    wont_decision = (
        f"Do not expand beyond {context['workflow_context']} or risk-bearing edge cases in this cycle."
        if not sparse
        else "Do not generate implementation scope from placeholder or missing brief fields."
    )

    return {
        "must_have": [
            _item(
                "SM-M1",
                "must_have",
                must_decision,
                _must_rationale(context, sparse),
                ["specific_user", "workflow_context", "mvp_scope"],
                evidence_ids,
                source_idea_ids,
                readiness + 16,
                sparse,
            )
        ],
        "should_have": [
            _item(
                "SM-S1",
                "should_have",
                should_decision,
                _should_rationale(context, sparse),
                ["buyer", "validation_plan", "first_milestones"],
                evidence_ids[:2] or evidence_ids,
                source_idea_ids,
                readiness + 4,
                sparse,
            )
        ],
        "could_have": [
            _item(
                "SM-C1",
                "could_have",
                could_decision,
                _could_rationale(context, sparse),
                ["source_idea_ids", "merged_product_concept"],
                evidence_ids[-2:] if len(evidence_ids) > 1 else evidence_ids,
                source_idea_ids,
                readiness - 8,
                sparse,
            )
        ],
        "wont_have_now": [
            _item(
                "SM-W1",
                "wont_have_now",
                wont_decision,
                _wont_rationale(context, sparse),
                ["risks", "readiness_score", "validation_plan"],
                evidence_ids,
                source_idea_ids,
                readiness - 4,
                sparse,
            )
        ],
    }


def _item(
    id: str,
    bucket: str,
    decision: str,
    rationale: str,
    dependencies: list[str],
    evidence_refs: list[str],
    source_idea_ids: list[str],
    score: float,
    force_low: bool,
) -> dict[str, Any]:
    return {
        "id": id,
        "bucket": bucket,
        "decision": decision,
        "rationale": rationale,
        "dependencies": dependencies,
        "evidence_refs": sorted(dict.fromkeys(evidence_refs)),
        "source_idea_ids": source_idea_ids,
        "confidence": _confidence(score, bool(evidence_refs), force_low),
    }


def _scope_context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    assumptions = _dedupe(
        [
            *_string_list(design_brief.get("why_this_now")),
            *_string_list(design_brief.get("synthesis_rationale")),
            *_field_values(source_ideas, "why_now"),
            *_field_values(source_ideas, "evidence_rationale"),
        ]
    )
    return {
        "domain": _clean(design_brief.get("domain")) or "general",
        "theme": _clean(design_brief.get("theme")),
        "readiness_score": float(design_brief.get("readiness_score") or 0.0),
        "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "TBD buyer"),
        "specific_user": _first_text(
            design_brief.get("specific_user"),
            _field_values(source_ideas, "specific_user"),
            "target user",
        ),
        "workflow_context": _first_text(
            design_brief.get("workflow_context"),
            _field_values(source_ideas, "workflow_context"),
            design_brief.get("theme"),
            "target workflow",
        ),
        "product_concept": _first_text(
            design_brief.get("merged_product_concept"),
            _field_values(source_ideas, "solution"),
            design_brief.get("title"),
        ),
        "mvp_scope": _string_list(design_brief.get("mvp_scope")),
        "first_milestones": _string_list(design_brief.get("first_milestones")),
        "validation_plan": _clean(design_brief.get("validation_plan")),
        "risks": risks,
        "assumptions": assumptions,
    }


def _must_rationale(context: dict[str, Any], sparse: bool) -> str:
    if sparse:
        return "The brief lacks enough concrete user, buyer, workflow, or MVP detail to create a reliable build boundary."
    scope = context["mvp_scope"][0] if context["mvp_scope"] else context["product_concept"]
    return f"This is the smallest defensible scope because it anchors the product concept to {scope}."


def _should_rationale(context: dict[str, Any], sparse: bool) -> str:
    if sparse:
        return "Validation support should remain conditional so agents do not turn incomplete context into commitments."
    validation = context["validation_plan"] or "the stated validation plan"
    return f"This should follow the must-have workflow because {validation} needs reviewable proof and milestone tracking."


def _could_rationale(context: dict[str, Any], sparse: bool) -> str:
    if sparse:
        return "Optional work is intentionally framed as deferred until source evidence and scope fields are filled."
    assumptions = context["assumptions"][0] if context["assumptions"] else context["product_concept"]
    return f"This can wait because it depends on the assumption that {assumptions}"


def _wont_rationale(context: dict[str, Any], sparse: bool) -> str:
    if sparse:
        return "The matrix should block speculative scope expansion when required inputs are missing."
    risk = context["risks"][0] if context["risks"] else "unvalidated adoption, workflow, or operational risk"
    return f"This is out of scope now because the current cycle should retire {risk} before expanding."


def _missing_inputs(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for field, reason in _REQUIRED_FIELDS:
        value = design_brief.get(field)
        if field == "source_idea_ids":
            is_missing = not source_ideas
        elif field in {"mvp_scope", "risks"}:
            is_missing = not _string_list(value)
        else:
            is_missing = not _clean(value)
        if is_missing:
            missing.append({"field": field, "reason": reason})
    return missing


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
            ideas.append({"id": str(idea_id), "missing": True})
            continue
        data = unit.model_dump(mode="json")
        relationship = relationship_by_id.get(str(idea_id), {})
        data["role"] = relationship.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _evidence_references(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal_ids: set[str] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        signal_ids.update(_string_list(idea.get("evidence_signals")))

    references: list[dict[str, Any]] = []
    for signal_id in sorted(signal_ids):
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        references.append(
            {
                "id": signal.id,
                "source_type": _source_type(signal),
                "source_adapter": str(getattr(signal, "source_adapter", "") or "unknown"),
                "title": signal.title,
                "url": signal.url,
                "credibility": round(float(signal.credibility or 0.0), 2),
                "tags": list(signal.tags),
            }
        )
    references.sort(key=lambda item: item["id"])
    return references


def _source_type(signal: Any) -> str:
    source_type = getattr(signal, "source_type", "")
    return str(getattr(source_type, "value", source_type) or "unknown")


def _source_idea_ids(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    return ids or [str(idea_id) for idea_id in design_brief.get("source_idea_ids") or []]


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        value = idea.get(field)
        if isinstance(value, list):
            values.extend(_string_list(value))
        elif _clean(value):
            values.append(_clean(value))
    return values


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _confidence(score: float, has_evidence: bool, force_low: bool) -> str:
    if force_low:
        return "low"
    if score >= 82 and has_evidence:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _overall_confidence(items: list[dict[str, Any]], missing_inputs: list[dict[str, str]]) -> str:
    if missing_inputs:
        return "low"
    if items and all(item["confidence"] in {"high", "medium"} for item in items):
        return "high" if items[0]["confidence"] == "high" else "medium"
    return "low"


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "None"


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
