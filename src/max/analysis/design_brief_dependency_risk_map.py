"""Deterministic dependency risk maps for persisted design briefs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.dependency_risk_map"
SCHEMA_VERSION = "max.design_brief.dependency_risk_map.v1"

RISK_CATEGORIES: tuple[str, ...] = (
    "vendor/API dependency",
    "data dependency",
    "compliance dependency",
    "staffing dependency",
    "launch dependency",
)

_VENDOR_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("Salesforce", "salesforce"),
    ("Slack", "slack"),
    ("Stripe", "stripe"),
    ("GitHub", "github"),
    ("Linear", "linear"),
    ("Jira", "jira"),
    ("OAuth or SSO provider", "oauth"),
    ("webhook API", "webhook"),
    ("external API", "api"),
    ("partner system", "partner"),
    ("vendor service", "vendor"),
)


@dataclass(frozen=True)
class DependencyRiskEntry:
    id: str
    dependency_name: str
    risk_category: str
    severity: str
    owner: str
    mitigation: str
    evidence_reference_id: str
    evidence_reference_summary: str
    source_fields: list[str]
    source_idea_ids: list[str]


def build_design_brief_dependency_risk_map(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a dependency risk map from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    context = _dependency_context(design_brief, source_ideas)
    evidence_references = _evidence_references(design_brief, source_ideas)
    risks = [
        asdict(entry)
        for entry in _risk_entries(design_brief, source_idea_ids, context, evidence_references)
    ]

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
        },
        "summary": {
            "risk_count": len(risks),
            "high_severity_count": sum(1 for risk in risks if risk["severity"] == "high"),
            "category_count": len({risk["risk_category"] for risk in risks}),
            "source_reference_count": len(evidence_references),
            "fallbacks_used": context["fallbacks_used"],
        },
        "dependency_context": context,
        "dependency_risks": risks,
        "evidence_references": evidence_references,
        "source_ideas": source_ideas,
    }


def render_design_brief_dependency_risk_map(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a dependency risk map as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported dependency risk map format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Dependency Risk Map: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Risk entries: {summary['risk_count']}",
        f"High severity: {summary['high_severity_count']}",
        "",
        "## Dependency Risks",
        "",
    ]

    for risk in report["dependency_risks"]:
        lines.extend(
            [
                f"### {risk['id']}: {risk['dependency_name']}",
                "",
                f"- Risk category: {risk['risk_category']}",
                f"- Severity: {risk['severity']}",
                f"- Owner: {risk['owner']}",
                f"- Mitigation: {risk['mitigation']}",
                f"- Evidence reference: {risk['evidence_reference_id']} - {risk['evidence_reference_summary']}",
                f"- Source fields: {_inline_list(risk['source_fields'])}",
                f"- Source ideas: {_inline_list(risk['source_idea_ids'])}",
                "",
            ]
        )

    lines.extend(["## Evidence References", ""])
    if report["evidence_references"]:
        for reference in report["evidence_references"]:
            lines.append(f"- **{reference['id']}** ({reference['type']}): {reference['summary']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def dependency_risk_map_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-dependency-risk-map.{extension}"
    )


def _risk_entries(
    design_brief: dict[str, Any],
    source_idea_ids: list[str],
    context: dict[str, Any],
    evidence_references: list[dict[str, Any]],
) -> list[DependencyRiskEntry]:
    evidence_by_id = {reference["id"]: reference for reference in evidence_references}
    vendor_names = _vendor_names(context["text_corpus"])
    primary_vendor = ", ".join(vendor_names[:3]) if vendor_names else "External API or vendor service"
    data_subject = (
        "Customer workflow data"
        if _has_any(context["text_corpus"], ("customer", "user", "personal", "account"))
        else "Workflow source data"
    )
    compliance_name = (
        "Security, privacy, and compliance review"
        if _has_any(context["text_corpus"], ("security", "privacy", "legal", "compliance"))
        else "Pre-launch policy review"
    )
    launch_name = (
        context["first_milestone"] if context["first_milestone"] else "First controlled launch"
    )

    return [
        DependencyRiskEntry(
            id="DBDR1",
            dependency_name=primary_vendor,
            risk_category="vendor/API dependency",
            severity="high" if vendor_names else "medium",
            owner="Engineering owner",
            mitigation=(
                f"Confirm sandbox access, API limits, authentication, retry behavior, and fallback path for {primary_vendor}."
            ),
            **_evidence(
                evidence_by_id,
                ["design_brief.merged_product_concept", "design_brief.mvp_scope"],
            ),
            source_fields=["merged_product_concept", "mvp_scope", "tech_approach", "suggested_stack"],
            source_idea_ids=source_idea_ids,
        ),
        DependencyRiskEntry(
            id="DBDR2",
            dependency_name=data_subject,
            risk_category="data dependency",
            severity="high" if _has_any(context["text_corpus"], ("customer", "personal", "privacy")) else "medium",
            owner="Data owner",
            mitigation=(
                "Document required fields, source of truth, retention needs, fixture data, and reconciliation checks before build handoff."
            ),
            **_evidence(evidence_by_id, ["design_brief.synthesis_rationale", "design_brief.mvp_scope"]),
            source_fields=["workflow_context", "mvp_scope", "synthesis_rationale", "risks"],
            source_idea_ids=source_idea_ids,
        ),
        DependencyRiskEntry(
            id="DBDR3",
            dependency_name=compliance_name,
            risk_category="compliance dependency",
            severity="high" if _has_any(context["text_corpus"], ("security", "privacy", "legal", "compliance")) else "medium",
            owner="Compliance owner",
            mitigation=(
                "Route security, privacy, legal, and procurement assumptions to accountable reviewers with explicit approval criteria."
            ),
            **_evidence(evidence_by_id, ["design_brief.risks", "design_brief.validation_plan"]),
            source_fields=["risks", "validation_plan", "domain_risks", "buyer"],
            source_idea_ids=source_idea_ids,
        ),
        DependencyRiskEntry(
            id="DBDR4",
            dependency_name="Implementation, validation, and support coverage",
            risk_category="staffing dependency",
            severity="high" if context["missing_owner_inputs"] else "medium",
            owner="Product lead",
            mitigation=(
                "Name implementation, validation, buyer, and support owners; record backup coverage for launch-critical paths."
            ),
            **_evidence(evidence_by_id, ["design_brief.validation_plan", "design_brief.why_this_now"]),
            source_fields=["buyer", "specific_user", "workflow_context", "validation_plan"],
            source_idea_ids=source_idea_ids,
        ),
        DependencyRiskEntry(
            id="DBDR5",
            dependency_name=launch_name,
            risk_category="launch dependency",
            severity=_launch_severity(design_brief),
            owner="Launch owner",
            mitigation=(
                "Define launch gate, pilot cohort, monitoring, rollback trigger, and next-decision evidence before autonomous execution."
            ),
            **_evidence(evidence_by_id, ["design_brief.first_milestones", "design_brief.validation_plan"]),
            source_fields=["first_milestones", "validation_plan", "design_status", "readiness_score"],
            source_idea_ids=source_idea_ids,
        ),
    ]


def _dependency_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    target_user = _first_with_fallback(
        fallbacks,
        "specific_user",
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        f"{title} user",
    )
    buyer = _first_with_fallback(
        fallbacks,
        "buyer",
        design_brief.get("buyer"),
        _field_values(source_ideas, "buyer"),
        "accountable sponsor",
    )
    workflow = _first_with_fallback(
        fallbacks,
        "workflow_context",
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        f"{title} workflow",
    )
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    milestones = _string_list(design_brief.get("first_milestones"))
    text_corpus = _dedupe(
        [
            title,
            design_brief.get("domain", ""),
            design_brief.get("theme", ""),
            design_brief.get("why_this_now", ""),
            design_brief.get("merged_product_concept", ""),
            design_brief.get("synthesis_rationale", ""),
            design_brief.get("validation_plan", ""),
            target_user,
            buyer,
            workflow,
            *_string_list(design_brief.get("mvp_scope")),
            *milestones,
            *risks,
            *_field_values(source_ideas, "problem"),
            *_field_values(source_ideas, "solution"),
            *_field_values(source_ideas, "current_workaround"),
            *_field_values(source_ideas, "tech_approach"),
            *_stack_values(source_ideas),
        ]
    )
    missing_owner_inputs = [
        field
        for field, value in (
            ("buyer", buyer if "buyer" not in fallbacks else ""),
            ("specific_user", target_user if "specific_user" not in fallbacks else ""),
            ("workflow_context", workflow if "workflow_context" not in fallbacks else ""),
            ("validation_plan", _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan"))),
        )
        if not value
    ]

    return {
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "first_milestone": milestones[0] if milestones else "",
        "risks": risks,
        "detected_vendors": _vendor_names(text_corpus),
        "missing_owner_inputs": missing_owner_inputs,
        "fallbacks_used": fallbacks,
        "text_corpus": text_corpus,
    }


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    for field in (
        "why_this_now",
        "merged_product_concept",
        "synthesis_rationale",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    ):
        values = _string_list(design_brief.get(field))
        if values:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": "; ".join(values),
                    "source_idea_ids": source_idea_ids,
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
    if not refs:
        refs.append(
            {
                "id": "design_brief",
                "type": "brief",
                "summary": "Sparse design brief with no explicit dependency evidence fields.",
                "source_idea_ids": source_idea_ids,
            }
        )
    return _dedupe_refs(refs)


def _evidence(
    evidence_by_id: dict[str, dict[str, Any]],
    preferred_ids: list[str],
) -> dict[str, str]:
    for reference_id in preferred_ids:
        reference = evidence_by_id.get(reference_id)
        if reference:
            return {
                "evidence_reference_id": reference_id,
                "evidence_reference_summary": str(reference["summary"]),
            }
    reference_id, reference = next(iter(evidence_by_id.items()))
    return {
        "evidence_reference_id": reference_id,
        "evidence_reference_summary": str(reference["summary"]),
    }


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


def _source_idea_ids(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    return ids or [str(idea_id) for idea_id in design_brief.get("source_idea_ids") or []]


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _stack_values(source_ideas: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        stack = idea.get("suggested_stack")
        if isinstance(stack, dict):
            values.extend(str(value) for value in stack.values() if value)
    return _dedupe(values)


def _vendor_names(values: list[str]) -> list[str]:
    text = " ".join(values).lower()
    return [name for name, keyword in _VENDOR_KEYWORDS if keyword in text]


def _has_any(values: list[str], terms: tuple[str, ...]) -> bool:
    text = " ".join(values).lower()
    return any(term in text for term in terms)


def _launch_severity(design_brief: dict[str, Any]) -> str:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    status = str(design_brief.get("design_status") or "").lower()
    if readiness < 60 or status in {"draft", "candidate"}:
        return "high"
    if readiness < 80:
        return "medium"
    return "medium"


def _first_with_fallback(
    fallbacks: list[str],
    label: str,
    *values: Any,
) -> str:
    for value in values[:-1]:
        text = _first_text(value)
        if text:
            return text
    fallbacks.append(label)
    return str(values[-1])


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
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return values
    return [str(value).strip()] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault(ref["id"], ref)
    return list(deduped.values())


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return cleaned or "design-brief"
