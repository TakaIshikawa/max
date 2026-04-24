"""Design-brief-level risk register aggregation."""

from __future__ import annotations

import json
import re
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.risk_register.v1"

RISK_CATEGORIES = (
    "market",
    "workflow",
    "technical",
    "data",
    "compliance",
    "dependency",
    "evidence",
)

_CATEGORY_KEYWORDS = {
    "compliance": ("compliance", "legal", "regulation", "regulated", "privacy", "pii", "hipaa", "gdpr"),
    "market": ("market", "buyer", "customer", "competition", "willingness", "pricing", "segment"),
    "data": ("data", "dataset", "signal", "evidence", "quality", "stale", "credibility"),
    "dependency": ("dependency", "adapter", "api", "vendor", "platform", "integration", "churn", "third-party"),
    "technical": ("technical", "architecture", "latency", "scale", "security", "implementation", "stack"),
    "workflow": ("workflow", "adoption", "handoff", "process", "operator", "user", "workaround"),
}


def build_design_brief_risk_register(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a consolidated risk register from a persisted brief and linked ideas."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    risks: list[dict[str, Any]] = []
    risks.extend(_brief_risks(design_brief))
    for idea in source_ideas:
        risks.extend(_idea_risks(idea))
    risks.extend(_structural_risks(design_brief, source_ideas))

    deduped = _prioritize(_dedupe(risks))
    return {
        "schema_version": SCHEMA_VERSION,
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
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": [idea["id"] for idea in source_ideas],
        },
        "summary": {
            "risk_count": len(deduped),
            "high_risk_count": sum(1 for risk in deduped if risk["severity"] == "high"),
            "medium_risk_count": sum(1 for risk in deduped if risk["severity"] == "medium"),
            "categories": sorted({risk["category"] for risk in deduped}),
            "top_risk_id": deduped[0]["id"] if deduped else None,
        },
        "risks": deduped,
        "validation_actions": [risk["validation_action"] for risk in deduped],
    }


def render_design_brief_risk_register(register: dict[str, Any], fmt: str = "json") -> str:
    """Render the risk register for MCP consumers."""
    if fmt == "json":
        return json.dumps(register, indent=2)
    if fmt != "markdown":
        raise ValueError(f"Unsupported risk register format: {fmt}")

    brief = register["design_brief"]
    lines = [
        f"# Risk Register: {brief['title']}",
        "",
        f"Schema: `{register['schema_version']}`",
        f"Risks: {register['summary']['risk_count']}",
        "",
    ]
    for risk in register["risks"]:
        lines.extend(
            [
                f"## {risk['priority']}. {risk['title']}",
                "",
                f"- Category: {risk['category']}",
                f"- Severity: {risk['severity']}",
                f"- Likelihood: {risk['likelihood']}",
                f"- Source ideas: {', '.join(risk['source_idea_ids']) or 'design brief'}",
                f"- Mitigation: {risk['mitigation']}",
                f"- Validation action: {risk['validation_action']}",
                "",
                risk["description"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _brief_risks(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _risk(
            title=_risk_title(text),
            description=text,
            category=_category_for(text),
            severity="high",
            likelihood="possible",
            source_idea_ids=list(design_brief.get("source_idea_ids") or []),
            source_fields=["design_brief.risks"],
        )
        for text in _string_list(design_brief.get("risks"))
        if _compact(text)
    ]


def _idea_risks(idea: dict[str, Any]) -> list[dict[str, Any]]:
    risks = [
        _risk(
            title=_risk_title(text),
            description=text,
            category=_category_for(text),
            severity="high",
            likelihood="possible",
            source_idea_ids=[idea["id"]],
            source_fields=["domain_risks"],
        )
        for text in _string_list(idea.get("domain_risks"))
        if _compact(text)
    ]

    field_risks = [
        (
            "specific_user",
            "Undefined specific user",
            "The source idea does not name a specific user persona, so implementation decisions may optimize for a generic audience.",
            "market",
        ),
        (
            "buyer",
            "Undefined buyer",
            "The source idea does not identify a buyer or sponsor, leaving adoption and budget risk unresolved.",
            "market",
        ),
        (
            "workflow_context",
            "Weak workflow context",
            "The source idea does not describe where the product fits into the user's workflow.",
            "workflow",
        ),
        (
            "tech_approach",
            "Unclear technical approach",
            "The source idea does not include a technical approach for implementers to validate.",
            "technical",
        ),
    ]
    for field, title, description, category in field_risks:
        if not _compact(idea.get(field)):
            risks.append(
                _risk(
                    title=title,
                    description=description,
                    category=category,
                    severity="medium",
                    likelihood="likely",
                    source_idea_ids=[idea["id"]],
                    source_fields=[field],
                )
            )
    return risks


def _structural_risks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    source_ids = [idea["id"] for idea in source_ideas]

    if len(source_ideas) < 2:
        risks.append(
            _risk(
                title="Single-source synthesis",
                description="The design brief is based on fewer than two persisted source ideas, limiting cross-idea validation.",
                category="evidence",
                severity="medium",
                likelihood="possible",
                source_idea_ids=source_ids,
                source_fields=["source_idea_ids"],
            )
        )

    ideas_with_evidence = [
        idea
        for idea in source_ideas
        if _string_list(idea.get("evidence_signals")) or _string_list(idea.get("inspiring_insights"))
    ]
    if len(ideas_with_evidence) < len(source_ideas):
        risks.append(
            _risk(
                title="Uneven source evidence",
                description="One or more source ideas lack linked signals or insights, so brief-level claims may rely on uneven evidence.",
                category="evidence",
                severity="medium",
                likelihood="likely",
                source_idea_ids=[
                    idea["id"]
                    for idea in source_ideas
                    if idea not in ideas_with_evidence
                ],
                source_fields=["evidence_signals", "inspiring_insights"],
            )
        )

    if not _compact(design_brief.get("validation_plan")):
        risks.append(
            _risk(
                title="Missing validation plan",
                description="The persisted design brief has no validation plan before implementation handoff.",
                category="evidence",
                severity="high",
                likelihood="likely",
                source_idea_ids=source_ids,
                source_fields=["design_brief.validation_plan"],
            )
        )

    return risks


def _risk(
    *,
    title: str,
    description: str,
    category: str,
    severity: str,
    likelihood: str,
    source_idea_ids: list[str],
    source_fields: list[str],
) -> dict[str, Any]:
    mitigation, validation_action = _actions(category, title)
    return {
        "id": "",
        "category": category if category in RISK_CATEGORIES else "evidence",
        "title": _compact(title),
        "description": _compact(description),
        "severity": severity,
        "likelihood": likelihood,
        "priority": 0,
        "source_idea_ids": sorted(set(source_idea_ids)),
        "source_fields": sorted(set(source_fields)),
        "mitigation": mitigation,
        "validation_action": validation_action,
    }


def _dedupe(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for risk in risks:
        key = f"{risk['category']}:{_fingerprint(risk['description']) or _fingerprint(risk['title'])}"
        if key not in deduped:
            deduped[key] = risk
            continue
        existing = deduped[key]
        existing["source_idea_ids"] = sorted(set(existing["source_idea_ids"]) | set(risk["source_idea_ids"]))
        existing["source_fields"] = sorted(set(existing["source_fields"]) | set(risk["source_fields"]))
        existing["severity"] = _max_severity(existing["severity"], risk["severity"])
        existing["likelihood"] = _max_likelihood(existing["likelihood"], risk["likelihood"])
    return list(deduped.values())


def _prioritize(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks.sort(
        key=lambda risk: (
            _severity_rank(risk["severity"]),
            _likelihood_rank(risk["likelihood"]),
            risk["category"],
            risk["title"],
        )
    )
    for priority, risk in enumerate(risks, start=1):
        risk["priority"] = priority
        risk["id"] = f"dbrr-{priority:03d}-{_slug(risk['category'])}-{_slug(risk['title'])[:36]}"
    return risks


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id = {source["idea_id"]: source for source in design_brief.get("sources", [])}
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
        if unit:
            ideas.append(unit.model_dump(mode="json"))
    return ideas


def _actions(category: str, title: str) -> tuple[str, str]:
    category_actions = {
        "market": (
            "Validate the buyer, target user, and willingness to adopt before committing build scope.",
            "Run discovery with at least three target accounts and record buyer, user, and urgency evidence.",
        ),
        "workflow": (
            "Map the target workflow and scope the MVP to one observable handoff or decision point.",
            "Reconstruct the current workflow with users and confirm where the product changes behavior.",
        ),
        "technical": (
            "Run a technical spike and convert unknowns into explicit acceptance criteria.",
            "Prototype the riskiest integration or architecture path before implementation planning.",
        ),
        "data": (
            "Separate claims supported by fresh data from assumptions that need more evidence.",
            "Refresh or add evidence signals for the affected claim and record credibility.",
        ),
        "compliance": (
            "Review the workflow with a domain-aware compliance owner and define launch gates.",
            "Document required compliance constraints before building user-facing flows.",
        ),
        "dependency": (
            "Pin critical dependencies and define fallback behavior for external API or platform changes.",
            "Test the core workflow against the dependency boundary and document failure handling.",
        ),
        "evidence": (
            "Attach independent evidence before treating the brief as build-ready.",
            "Resolve the evidence gap with source ideas, signals, or a validation result.",
        ),
    }
    return category_actions.get(category, category_actions["evidence"])


def _category_for(text: str) -> str:
    lowered = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "market"


def _risk_title(text: str) -> str:
    compact = _compact(text).rstrip(".")
    if not compact:
        return "Unspecified risk"
    first = re.split(r"[.;:]", compact, maxsplit=1)[0].strip()
    return first[:80]


def _fingerprint(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "risk"


def _max_severity(left: str, right: str) -> str:
    return left if _severity_rank(left) <= _severity_rank(right) else right


def _max_likelihood(left: str, right: str) -> str:
    return left if _likelihood_rank(left) <= _likelihood_rank(right) else right


def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)


def _likelihood_rank(value: str) -> int:
    return {"likely": 0, "possible": 1, "unlikely": 2}.get(value, 3)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [str(key) for key in value.keys()]
    return [str(item) for item in value if str(item).strip()]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
