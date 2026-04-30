"""Deterministic stakeholder map export for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any, Iterable

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.stakeholder_map.v1"


ROLE_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "buyer",
        "name": "Buyer",
        "fields": ("buyer",),
        "responsibilities": (
            "Own the business problem and define the required purchase outcome.",
            "Validate that the workflow priority maps to an active initiative or budget.",
        ),
        "keywords": ("buyer", "budget", "purchase", "market", "funding", "revenue"),
        "decision_power": "high",
    },
    {
        "id": "user",
        "name": "User",
        "fields": ("specific_user", "target_users"),
        "responsibilities": (
            "Run the day-to-day workflow and confirm usability constraints.",
            "Describe current workarounds, failure modes, and adoption friction.",
        ),
        "keywords": ("user", "workflow", "pain", "problem", "workaround"),
        "decision_power": "medium",
    },
    {
        "id": "economic_buyer",
        "name": "Economic Buyer",
        "fields": ("buyer",),
        "responsibilities": (
            "Approve paid pilots, renewal terms, and expansion thresholds.",
            "Compare the expected value against budget, risk, and competing priorities.",
        ),
        "keywords": ("funding", "budget", "pricing", "procurement", "purchase"),
        "decision_power": "high",
    },
    {
        "id": "implementer",
        "name": "Implementer",
        "fields": ("specific_user", "workflow_context", "tech_approach"),
        "responsibilities": (
            "Connect the product to the target workflow, systems, and data paths.",
            "Identify integration, rollout, and operational support requirements.",
        ),
        "keywords": ("implementation", "integration", "workflow", "api", "technical", "operator"),
        "decision_power": "medium",
    },
    {
        "id": "approver",
        "name": "Approver",
        "fields": ("buyer", "domain_risks", "risks"),
        "responsibilities": (
            "Accept or reject launch, security, compliance, and procurement gates.",
            "Set the conditions that must be satisfied before wider rollout.",
        ),
        "keywords": ("security", "privacy", "compliance", "approval", "risk", "legal"),
        "decision_power": "high",
    },
    {
        "id": "blocker",
        "name": "Blocker",
        "fields": ("domain_risks", "risks", "current_workaround"),
        "responsibilities": (
            "Surface reasons the deal, pilot, or adoption path could stall.",
            "Force proof around risk, switching cost, ownership, or competing tools.",
        ),
        "keywords": ("risk", "competition", "incumbent", "security", "procurement", "workaround"),
        "decision_power": "medium",
    },
    {
        "id": "champion",
        "name": "Champion",
        "fields": ("specific_user", "buyer", "validation_plan"),
        "responsibilities": (
            "Sponsor discovery access and translate pain into internal urgency.",
            "Recruit pilot users and help define a credible proof of value.",
        ),
        "keywords": ("validation", "pilot", "customer", "pain", "workflow", "adoption"),
        "decision_power": "medium",
    },
)


def build_design_brief_stakeholder_map(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a deterministic stakeholder map from stored design brief lineage."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    evidence = _evidence_references(store, source_ideas)
    evaluations = _evaluation_records(store, source_idea_ids)
    stakeholders = _stakeholders(design_brief, source_ideas, evidence, evaluations)
    unresolved_assumptions = _unresolved_assumptions(design_brief, stakeholders, evidence)
    confidence = _overall_confidence(design_brief, stakeholders, evidence, evaluations)
    interview_questions = _interview_questions(design_brief, stakeholders, unresolved_assumptions)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.stakeholder_map",
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
            "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer"),
            "specific_user": _first_text(
                design_brief.get("specific_user"),
                _field_values(source_ideas, "specific_user"),
                "target user",
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                _field_values(source_ideas, "workflow_context"),
                "target workflow",
            ),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "stakeholder_count": len(stakeholders),
            "inferred_role_count": sum(1 for stakeholder in stakeholders if stakeholder["inference_status"] == "inferred"),
            "evidence_reference_count": len(evidence),
            "evaluation_count": len(evaluations),
            "unresolved_assumption_count": len(unresolved_assumptions),
            "interview_question_count": len(interview_questions),
        },
        "stakeholders": stakeholders,
        "confidence": confidence,
        "evidence_references": evidence,
        "evaluations": evaluations,
        "unresolved_assumptions": unresolved_assumptions,
        "interview_questions": interview_questions,
        "source_ideas": source_ideas,
    }


def render_design_brief_stakeholder_map(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a stakeholder map as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported stakeholder map format: {fmt}")

    brief = report["design_brief"]
    confidence = report["confidence"]
    lines = [
        f"# Stakeholder Map: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Confidence: {confidence['level']} ({confidence['score']:.2f})",
        "",
        "## Stakeholders",
        "",
    ]

    for stakeholder in report["stakeholders"]:
        lines.extend(
            [
                f"### {stakeholder['role_name']}: {stakeholder['persona']}",
                "",
                f"- Decision power: {stakeholder['decision_power']}",
                f"- Inference status: {stakeholder['inference_status']}",
                f"- Confidence: {stakeholder['confidence']['level']} ({stakeholder['confidence']['score']:.2f})",
                f"- Source ideas: {_inline_ids(stakeholder['source_idea_ids'])}",
                f"- Evidence references: {_inline_ids(stakeholder['evidence_reference_ids'])}",
                "- Responsibilities:",
            ]
        )
        lines.extend(f"  - {responsibility}" for responsibility in stakeholder["responsibilities"])
        lines.append("- Assumptions:")
        lines.extend(f"  - {assumption}" for assumption in stakeholder["assumptions"])
        lines.append("")

    lines.extend(["## Unresolved Assumptions", ""])
    lines.extend(f"- {assumption}" for assumption in report["unresolved_assumptions"])

    lines.extend(["", "## Interview Questions", ""])
    lines.extend(f"- {question}" for question in report["interview_questions"])

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for reference in report["evidence_references"]:
            line = f"- `{reference['id']}` [{reference['source_type']}] {reference['title']}"
            if reference.get("url"):
                line += f" - {reference['url']}"
            lines.append(line)
    else:
        lines.append("- No stored evidence references are linked to the brief lineage.")
    return "\n".join(lines).rstrip() + "\n"


def stakeholder_map_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-stakeholder-map.{extension}"
    )


def _stakeholders(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stakeholders: list[dict[str, Any]] = []
    for config in ROLE_CONFIGS:
        persona = _persona_for_role(config["id"], design_brief, source_ideas)
        evidence_ids = _evidence_ids_for_keywords(evidence, config["keywords"])
        source_idea_ids = _source_ids_for_fields(source_ideas, config["fields"])
        assumptions = _role_assumptions(config["id"], persona, design_brief, source_ideas, evidence_ids)
        confidence = _role_confidence(config["id"], persona, source_idea_ids, evidence_ids, evaluations)
        stakeholders.append(
            {
                "role": config["id"],
                "role_name": config["name"],
                "persona": persona,
                "inference_status": "inferred" if confidence["score"] >= 0.45 else "needs_validation",
                "decision_power": config["decision_power"],
                "responsibilities": list(config["responsibilities"]),
                "assumptions": assumptions,
                "source_idea_ids": source_idea_ids,
                "evidence_reference_ids": evidence_ids,
                "confidence": confidence,
            }
        )
    return stakeholders


def _persona_for_role(
    role: str,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> str:
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer")
    user = _first_text(design_brief.get("specific_user"), _field_values(source_ideas, "specific_user"), "target user")
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        "target workflow",
    )
    risks = " ".join(_string_list(design_brief.get("risks")) + _joined_lists(source_ideas, "domain_risks")).lower()

    if role == "buyer":
        return buyer
    if role == "user":
        return user
    if role == "economic_buyer":
        if _looks_like_budget_owner(buyer):
            return buyer
        return f"budget owner for {buyer}"
    if role == "implementer":
        if _looks_like_technical_role(user):
            return user
        return f"implementation owner for {workflow}"
    if role == "approver":
        if any(term in risks for term in ("security", "privacy", "compliance", "legal")):
            return "security or compliance approver"
        return f"approval owner for {buyer}"
    if role == "blocker":
        if any(term in risks for term in ("security", "privacy", "compliance", "legal")):
            return "security, compliance, or procurement blocker"
        return "incumbent tool or workflow owner"
    if role == "champion":
        return user if user != "target user" else buyer
    return "stakeholder"


def _role_assumptions(
    role: str,
    persona: str,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_ids: list[str],
) -> list[str]:
    assumptions: list[str] = []
    if role in {"buyer", "economic_buyer"} and not _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer")):
        assumptions.append("Buyer is not explicitly named in the brief or source ideas.")
    if role in {"user", "champion", "implementer"} and not _first_text(
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
    ):
        assumptions.append("Primary user is not explicitly named in the brief or source ideas.")
    if role == "economic_buyer" and not _looks_like_budget_owner(persona):
        assumptions.append("Economic buyer is inferred from buyer context; budget authority needs validation.")
    if role == "approver":
        assumptions.append("Approval path is inferred from risks and evidence; named approvers need validation.")
    if role == "blocker":
        assumptions.append("Blocking power is inferred from risks, workarounds, and adoption constraints.")
    if not evidence_ids:
        assumptions.append("No direct stored evidence signal matched this stakeholder role.")
    return assumptions or ["Role is inferred from persisted brief and source idea fields."]


def _role_confidence(
    role: str,
    persona: str,
    source_idea_ids: list[str],
    evidence_ids: list[str],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    persona_score = 0.0 if persona.startswith(("target ", "budget owner for target")) else 0.35
    source_score = 0.20 if source_idea_ids else 0.0
    evidence_score = min(len(evidence_ids) / 3.0, 1.0) * 0.25
    evaluation_score = 0.20 if evaluations else 0.0
    if role in {"approver", "blocker"}:
        source_score = max(source_score, 0.10)
    score = round(min(persona_score + source_score + evidence_score + evaluation_score, 1.0), 2)
    return {
        "score": score,
        "level": "high" if score >= 0.75 else "medium" if score >= 0.45 else "low",
        "drivers": [
            f"persona={'present' if persona_score else 'fallback'}",
            f"source_ideas={len(source_idea_ids)}",
            f"evidence_references={len(evidence_ids)}",
            f"evaluations={len(evaluations)}",
        ],
    }


def _overall_confidence(
    design_brief: dict[str, Any],
    stakeholders: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness = min(max(float(design_brief.get("readiness_score") or 0.0) / 100.0, 0.0), 1.0)
    role_score = sum(item["confidence"]["score"] for item in stakeholders) / len(stakeholders)
    evidence_score = min(len(evidence) / 5.0, 1.0)
    evaluation_score = min(len(evaluations) / 2.0, 1.0)
    score = round(readiness * 0.25 + role_score * 0.40 + evidence_score * 0.20 + evaluation_score * 0.15, 2)
    return {
        "score": score,
        "level": "high" if score >= 0.75 else "medium" if score >= 0.45 else "low",
        "drivers": [
            f"readiness={readiness:.2f}",
            f"average_role_confidence={role_score:.2f}",
            f"evidence_references={len(evidence)}",
            f"evaluations={len(evaluations)}",
        ],
    }


def _unresolved_assumptions(
    design_brief: dict[str, Any],
    stakeholders: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[str]:
    assumptions: list[str] = []
    if not _clean(design_brief.get("buyer")):
        assumptions.append("Confirm the named buyer and whether they control budget.")
    if not _clean(design_brief.get("specific_user")):
        assumptions.append("Confirm the primary user and daily workflow owner.")
    if not evidence:
        assumptions.append("Attach persisted evidence signals to the source ideas before relying on this map.")
    for stakeholder in stakeholders:
        if stakeholder["confidence"]["level"] == "low":
            assumptions.append(f"Validate the {stakeholder['role_name'].lower()} persona: {stakeholder['persona']}.")
    assumptions.extend(_string_list(design_brief.get("risks"))[:3])
    return list(dict.fromkeys(assumptions))


def _interview_questions(
    design_brief: dict[str, Any],
    stakeholders: list[dict[str, Any]],
    assumptions: list[str],
) -> list[str]:
    by_role = {stakeholder["role"]: stakeholder for stakeholder in stakeholders}
    buyer = by_role["buyer"]["persona"]
    user = by_role["user"]["persona"]
    economic_buyer = by_role["economic_buyer"]["persona"]
    approver = by_role["approver"]["persona"]
    blocker = by_role["blocker"]["persona"]
    champion = by_role["champion"]["persona"]
    workflow = design_brief.get("workflow_context") or "the target workflow"
    questions = [
        f"What outcome would make {buyer} prioritize {design_brief['title']} this quarter?",
        f"How does {user} handle {workflow} today, and where does the current process fail?",
        f"Who besides {economic_buyer} must approve budget, procurement, security, or rollout?",
        f"What evidence would convince {approver} that the MVP is ready for a pilot?",
        f"What would cause {blocker} to stop or delay adoption?",
        f"Can {champion} recruit pilot users and define a measurable proof of value?",
    ]
    if assumptions:
        questions.append(f"Which assumption is wrong or missing: {assumptions[0]}")
    return questions


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
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
    for idea_id in ordered_ids:
        if not idea_id or str(idea_id) in seen:
            continue
        seen.add(str(idea_id))
        unit = store.get_buildable_unit(str(idea_id))
        relationship = relationship_by_id.get(str(idea_id), {})
        if not unit:
            ideas.append(
                {
                    "id": str(idea_id),
                    "role": relationship.get("role", "source"),
                    "rank": relationship.get("rank"),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = relationship.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _evidence_references(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal_source_ideas: dict[str, list[str]] = {}
    insight_ids: set[str] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        idea_id = str(idea["id"])
        for signal_id in _string_list(idea.get("evidence_signals")):
            signal_source_ideas.setdefault(signal_id, []).append(idea_id)
        insight_ids.update(_string_list(idea.get("inspiring_insights")))

    for insight_id in sorted(insight_ids):
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        source_ids = [
            str(idea["id"])
            for idea in source_ideas
            if insight_id in _string_list(idea.get("inspiring_insights"))
        ]
        for signal_id in _string_list(getattr(insight, "evidence", [])):
            signal_source_ideas.setdefault(signal_id, []).extend(source_ids)

    references: list[dict[str, Any]] = []
    for signal_id in sorted(signal_source_ideas):
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        references.append(
            {
                "id": signal.id,
                "kind": "signal",
                "source_type": _source_type(signal),
                "source_adapter": str(getattr(signal, "source_adapter", "") or "unknown"),
                "title": signal.title,
                "url": signal.url,
                "credibility": round(float(signal.credibility or 0.0), 2),
                "tags": list(signal.tags),
                "signal_role": str(getattr(signal, "signal_role", "") or ""),
                "source_idea_ids": sorted(set(signal_source_ideas.get(signal_id, []))),
            }
        )
    references.sort(key=lambda item: item["id"])
    return references


def _evaluation_records(store: Store, source_idea_ids: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idea_id in sorted(set(source_idea_ids)):
        evaluation = store.get_evaluation(idea_id)
        if not evaluation:
            continue
        records.append(
            {
                "source_idea_id": idea_id,
                "overall_score": round(float(evaluation.overall_score), 2),
                "pain_severity": round(float(evaluation.pain_severity.value), 2),
                "pain_severity_confidence": round(float(evaluation.pain_severity.confidence), 2),
                "addressable_scale": round(float(evaluation.addressable_scale.value), 2),
                "competitive_density": round(float(evaluation.competitive_density.value), 2),
                "recommendation": evaluation.recommendation,
            }
        )
    records.sort(key=lambda item: item["source_idea_id"])
    return records


def _evidence_ids_for_keywords(
    evidence: list[dict[str, Any]],
    keywords: Iterable[str],
) -> list[str]:
    matched: list[str] = []
    for reference in evidence:
        text = " ".join(
            [
                reference["title"],
                reference["source_type"],
                reference.get("signal_role", ""),
                " ".join(reference.get("tags", [])),
            ]
        ).lower()
        if any(keyword in text for keyword in keywords):
            matched.append(reference["id"])
    return matched


def _source_ids_for_fields(source_ideas: list[dict[str, Any]], fields: Iterable[str]) -> list[str]:
    ids = [
        str(idea["id"])
        for idea in source_ideas
        if not idea.get("missing") and any(_has_value(idea.get(field)) for field in fields)
    ]
    return list(dict.fromkeys(ids))


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    return [_clean(item.get(field)) for item in items if _clean(item.get(field))]


def _joined_lists(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        values.extend(_string_list(item.get(field)))
    return values


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
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean(value)] if _clean(value) else []
    if isinstance(value, dict):
        return [_clean(key) for key in value.keys() if _clean(key)]
    if isinstance(value, list | tuple | set):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _looks_like_budget_owner(value: str) -> bool:
    lowered = value.lower()
    return any(
        term in lowered
        for term in ("vp", "vice president", "chief", "head", "director", "manager", "lead", "founder", "owner")
    )


def _looks_like_technical_role(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ("engineer", "developer", "admin", "operator", "analyst", "architect"))


def _source_type(signal: Any) -> str:
    source_type = getattr(signal, "source_type", "")
    if hasattr(source_type, "value"):
        return str(source_type.value).lower()
    return str(source_type or "").lower()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "design-brief"
