"""Deterministic market-entry risk reports for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.market_entry_risk"
SCHEMA_VERSION = "max.design_brief.market_entry_risk.v1"

_VALIDATED_STATUSES = {"approved", "validated", "ready", "launched", "active"}
_WEAK_STATUSES = {"draft", "candidate", "proposed", "backlog", "new"}

_ADOPTION_TERMS = (
    "adoption",
    "onboarding",
    "training",
    "manual",
    "change management",
    "new workflow",
    "workflow change",
)
_COMPETITION_TERMS = (
    "competitor",
    "competition",
    "incumbent",
    "crowded",
    "alternative",
    "platform",
    "suite",
)
_CHANNEL_TERMS = (
    "channel",
    "partner",
    "marketplace",
    "sales",
    "first 10",
    "community",
    "distribution",
    "customer",
)
_SWITCHING_TERMS = (
    "switching",
    "migration",
    "integration",
    "import",
    "data",
    "handoff",
    "legacy",
    "dependency",
)
_COMPLIANCE_TERMS = (
    "compliance",
    "legal",
    "regulation",
    "regulated",
    "privacy",
    "pii",
    "hipaa",
    "gdpr",
    "security",
    "soc2",
)
_TIMING_TERMS = (
    "deadline",
    "urgent",
    "now",
    "mandate",
    "launch",
    "regulation",
    "renewal",
    "budget cycle",
)
_LOW_FRICTION_TERMS = (
    "self-serve",
    "existing workflow",
    "no migration",
    "low-friction",
    "validated",
    "pilot",
    "weekly",
    "recurring",
)


def build_design_brief_market_entry_risk_report(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a market-entry risk report from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas] or _string_list(
        design_brief.get("source_idea_ids")
    )
    prior_art = _prior_art_records(store, source_idea_ids)
    context = _market_context(design_brief, source_ideas, prior_art)
    risks = [
        _adoption_friction_risk(context),
        _incumbent_competition_risk(context),
        _channel_access_risk(context),
        _switching_costs_risk(context),
        _compliance_constraints_risk(context),
        _timing_sensitivity_risk(context),
    ]
    score = _risk_score(risks)
    risk_band = _risk_band(score)

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
            "score": score,
            "risk_band": risk_band,
            "high_risk_count": sum(1 for risk in risks if risk["severity"] == "high"),
            "medium_risk_count": sum(1 for risk in risks if risk["severity"] == "medium"),
            "low_risk_count": sum(1 for risk in risks if risk["severity"] == "low"),
            "primary_risk_category": _primary_risk_category(risks),
            "fallbacks_used": context["fallbacks_used"],
            "open_question_count": sum(1 for risk in risks if risk["open_question"]),
        },
        "market_context": context,
        "risks": risks,
        "mitigation_plan": _mitigation_plan(risks),
        "open_questions": _open_questions(risks),
        "signals": {
            "prior_art": prior_art,
            "source_ideas": source_ideas,
        },
    }


def render_design_brief_market_entry_risk_report(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a market-entry risk report as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported market entry risk report format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Market Entry Risk Report: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Design brief: `{brief['id']}`",
        f"Risk band: `{summary['risk_band']}`",
        f"Score: {summary['score']}/100",
        f"Primary risk: `{summary['primary_risk_category']}`",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
        "## Market Context",
        "",
        f"- Buyer: {report['market_context']['buyer']}",
        f"- User: {report['market_context']['target_user']}",
        f"- Workflow: {report['market_context']['workflow_context']}",
        f"- Value proposition: {report['market_context']['value_proposition']}",
        f"- Current workaround: {report['market_context']['current_workaround']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Risk Entries",
        "",
    ]
    for risk in report["risks"]:
        lines.extend(
            [
                f"### {risk['title']}",
                "",
                f"- Category: {risk['category']}",
                f"- Severity: {risk['severity']}",
                f"- Evidence: {'; '.join(risk['evidence'])}",
                f"- Mitigation: {risk['mitigation']}",
                f"- Open question: {risk['open_question'] or 'none'}",
                "",
            ]
        )

    lines.extend(["## Mitigation Plan", ""])
    for item in report["mitigation_plan"]:
        lines.append(f"- **{item['owner_role']}**: {item['action']} ({item['addresses']})")

    lines.extend(["", "## Open Questions", ""])
    if report["open_questions"]:
        for question in report["open_questions"]:
            lines.append(f"- **{question['category']}**: {question['question']}")
    else:
        lines.append("- No blocking market-entry questions were identified.")

    return "\n".join(lines).rstrip() + "\n"


def market_entry_risk_report_filename(
    design_brief: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'market-entry-risk'))}-"
        f"market-entry-risk.{extension}"
    )


def _market_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    prior_art: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("economic buyer", "explicit_fallback"),
    )
    target_user = _first_with_label(
        fallbacks,
        "target_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    value = _first_with_label(
        fallbacks,
        "value_proposition",
        (design_brief.get("value_proposition"), "design_brief.value_proposition"),
        (lead_idea and lead_idea.get("value_proposition"), "lead_idea.value_proposition"),
        (_field_values(source_ideas, "value_proposition"), "source_ideas.value_proposition"),
        (design_brief.get("merged_product_concept"), "design_brief.merged_product_concept"),
        (f"Improve {workflow}", "explicit_fallback"),
    )
    workaround = _first_with_label(
        fallbacks,
        "current_workaround",
        (design_brief.get("current_workaround"), "design_brief.current_workaround"),
        (lead_idea and lead_idea.get("current_workaround"), "lead_idea.current_workaround"),
        (_field_values(source_ideas, "current_workaround"), "source_ideas.current_workaround"),
        ("manual process or incumbent tool", "explicit_fallback"),
    )
    first_customers = _first_text(
        design_brief.get("first_10_customers"),
        lead_idea and lead_idea.get("first_10_customers"),
        *_field_values(source_ideas, "first_10_customers"),
    )
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        *_field_values(source_ideas, "validation_plan"),
    )
    why_now = _first_text(
        design_brief.get("why_this_now"),
        lead_idea and lead_idea.get("why_now"),
        *_field_values(source_ideas, "why_now"),
    )
    risks = _dedupe(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
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
                *[
                    idea.get(field)
                    for idea in source_ideas
                    for field in (
                        "problem",
                        "solution",
                        "value_proposition",
                        "specific_user",
                        "buyer",
                        "workflow_context",
                        "current_workaround",
                        "why_now",
                        "first_10_customers",
                        "validation_plan",
                        "domain_risks",
                        "evidence_rationale",
                    )
                ],
                *[item.get("title") for item in prior_art],
                *[item.get("description") for item in prior_art],
            ]
        )
    )
    return {
        "buyer": buyer,
        "target_user": target_user,
        "workflow_context": workflow,
        "value_proposition": value,
        "current_workaround": workaround,
        "first_customers": first_customers,
        "validation_plan": validation_plan,
        "why_now": why_now,
        "risks": risks,
        "design_status": str(design_brief.get("design_status") or ""),
        "readiness_score": float(design_brief.get("readiness_score") or 0.0),
        "prior_art_count": len(prior_art),
        "source_idea_ids": [idea["id"] for idea in source_ideas],
        "fallbacks_used": fallbacks,
        "text": text.lower(),
    }


def _adoption_friction_risk(context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    points = 0
    if _has_any(context["text"], _ADOPTION_TERMS):
        points += 25
        evidence.append("Context mentions adoption, onboarding, training, or workflow-change friction.")
    if _is_fallback(context, "target_user") or _is_fallback(context, "workflow_context"):
        points += 35
        evidence.append("Target user or workflow context required fallback assumptions.")
    if not context["validation_plan"]:
        points += 20
        evidence.append("No adoption validation plan is attached to the brief lineage.")
    if _has_any(context["text"], _LOW_FRICTION_TERMS):
        points -= 20
        evidence.append("Context includes low-friction, recurring, pilot, or existing-workflow signals.")
    return _risk(
        category="adoption_friction",
        title="Adoption Friction",
        points=points,
        evidence=evidence,
        mitigation="Run workflow walkthroughs with target users and remove onboarding steps that are not essential for first value.",
        open_question=(
            "Which user segment can reach first value without a high-touch onboarding path?"
            if points >= 35
            else ""
        ),
    )


def _incumbent_competition_risk(context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    points = context["prior_art_count"] * 25
    if context["prior_art_count"]:
        evidence.append(f"{context['prior_art_count']} prior-art record(s) are linked to source ideas.")
    if _has_any(context["text"], _COMPETITION_TERMS):
        points += 35
        evidence.append("Context references incumbents, competitors, alternatives, platforms, or suites.")
    if "differentiated" in context["text"] or "underserved" in context["text"]:
        points -= 15
        evidence.append("Context names a differentiation or underserved-segment angle.")
    return _risk(
        category="incumbent_competition",
        title="Incumbent Competition",
        points=points,
        evidence=evidence,
        mitigation="Position around the narrow workflow gap incumbents do not solve and collect proof that buyers will not wait for suite vendors.",
        open_question=(
            "Which incumbent or workaround does the buyer compare against during budget approval?"
            if points >= 35
            else ""
        ),
    )


def _channel_access_risk(context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    points = 0
    if not context["first_customers"]:
        points += 35
        evidence.append("No first-customer or initial channel description is available.")
    if _is_fallback(context, "buyer"):
        points += 25
        evidence.append("Buyer identity required a fallback assumption.")
    has_enterprise_gate = _has_any(
        context["text"],
        ("procurement", "enterprise", "security review", "approval"),
    )
    if has_enterprise_gate:
        points += 55
        evidence.append("Context implies enterprise approval or procurement access constraints.")
    if _has_any(context["text"], _CHANNEL_TERMS) and context["first_customers"] and not has_enterprise_gate:
        points -= 20
        evidence.append("Context names a customer, partner, community, marketplace, or sales access path.")
    return _risk(
        category="channel_access",
        title="Channel Access",
        points=points,
        evidence=evidence,
        mitigation="Define the first reachable segment, acquisition motion, and named buyer path before committing launch scope.",
        open_question=(
            "What is the first repeatable channel that can reach the economic buyer?"
            if points >= 35
            else ""
        ),
    )


def _switching_costs_risk(context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    points = 0
    if _has_any(context["text"], _SWITCHING_TERMS):
        points += 40
        evidence.append("Context references migration, integration, data, dependency, or handoff work.")
    if "manual" in context["current_workaround"].lower():
        points += 15
        evidence.append("The current workaround is manual, which may hide process-change cost.")
    if _has_any(context["text"], ("no migration", "drop-in", "existing workflow", "no data import")):
        points -= 25
        evidence.append("Context includes drop-in, no-migration, or existing-workflow positioning.")
    return _risk(
        category="switching_costs",
        title="Switching Costs",
        points=points,
        evidence=evidence,
        mitigation="Ship a migration-light path with import limits, integration boundaries, and a rollback story for early adopters.",
        open_question=(
            "What data, integration, or process commitment must a customer make before first value?"
            if points >= 35
            else ""
        ),
    )


def _compliance_constraints_risk(context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    points = 0
    if _has_any(context["text"], _COMPLIANCE_TERMS):
        points += 45
        evidence.append("Context references compliance, legal, privacy, security, or regulated-market constraints.")
    if _has_any(context["text"], ("internal productivity", "no pii", "non-regulated", "public data")):
        points -= 20
        evidence.append("Context includes non-regulated, no-PII, public-data, or internal-productivity signals.")
    return _risk(
        category="compliance_constraints",
        title="Compliance Constraints",
        points=points,
        evidence=evidence,
        mitigation="Document data handling, review obligations, and any launch-blocking compliance checkpoints before pilot commitments.",
        open_question=(
            "Which compliance review can block initial deployment or paid conversion?"
            if points >= 35
            else ""
        ),
    )


def _timing_sensitivity_risk(context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    points = 0
    if not context["why_now"]:
        points += 30
        evidence.append("No why-now signal is attached to the brief lineage.")
    if context["design_status"].lower() in _WEAK_STATUSES:
        points += 20
        evidence.append(f"Design status is `{context['design_status'] or 'unknown'}`.")
    if _has_any(context["text"], _TIMING_TERMS):
        points += 25
        evidence.append("Context references deadlines, urgency, mandates, launches, renewals, or budget cycles.")
    if context["design_status"].lower() in _VALIDATED_STATUSES and context["readiness_score"] >= 75:
        points -= 25
        evidence.append("Validated status and readiness score reduce timing uncertainty.")
    return _risk(
        category="timing_sensitivity",
        title="Timing Sensitivity",
        points=points,
        evidence=evidence,
        mitigation="Tie launch timing to a concrete external event and define what slips if that event moves.",
        open_question=(
            "What external deadline or market change makes entry urgent now?"
            if points >= 35
            else ""
        ),
    )


def _risk(
    *,
    category: str,
    title: str,
    points: int,
    evidence: list[str],
    mitigation: str,
    open_question: str,
) -> dict[str, Any]:
    bounded = max(0, min(100, points))
    severity = "high" if bounded >= 55 else "medium" if bounded >= 30 else "low"
    if not evidence:
        evidence = ["No explicit risk signal found; severity is based on available structured context."]
    return {
        "id": category,
        "category": category,
        "title": title,
        "severity": severity,
        "score": bounded,
        "evidence": evidence,
        "mitigation": mitigation,
        "open_question": open_question,
    }


def _risk_score(risks: list[dict[str, Any]]) -> int:
    if not risks:
        return 0
    average = int(round(sum(float(risk["score"]) for risk in risks) / len(risks)))
    high_count = sum(1 for risk in risks if risk["severity"] == "high")
    medium_count = sum(1 for risk in risks if risk["severity"] == "medium")
    if high_count >= 2 and medium_count >= 2:
        return max(55, average)
    return average


def _risk_band(score: int) -> str:
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _primary_risk_category(risks: list[dict[str, Any]]) -> str:
    return max(risks, key=lambda risk: (risk["score"], risk["category"]))["category"]


def _mitigation_plan(risks: list[dict[str, Any]]) -> list[dict[str, str]]:
    prioritized = sorted(risks, key=lambda risk: (-risk["score"], risk["category"]))[:4]
    return [
        {
            "id": f"MR{i}",
            "owner_role": _owner_for(risk["category"]),
            "addresses": risk["category"],
            "action": risk["mitigation"],
        }
        for i, risk in enumerate(prioritized, start=1)
    ]


def _open_questions(risks: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"category": risk["category"], "question": risk["open_question"]}
        for risk in risks
        if risk["open_question"]
    ]


def _owner_for(category: str) -> str:
    return {
        "adoption_friction": "Product",
        "incumbent_competition": "Product Marketing",
        "channel_access": "Go-to-Market",
        "switching_costs": "Solutions",
        "compliance_constraints": "Legal/Security",
        "timing_sensitivity": "Strategy",
    }.get(category, "Product")


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
        get_matches = getattr(store, "get_prior_art_matches", None)
        if not get_matches:
            continue
        for match in get_matches(idea_id):
            records.append(
                {
                    "id": match["id"],
                    "source_idea_id": idea_id,
                    "source": match.get("source", ""),
                    "title": match.get("title", ""),
                    "url": match.get("url", ""),
                    "description": match.get("description", ""),
                    "relevance_score": round(float(match.get("relevance_score") or 0.0), 3),
                }
            )
    records.sort(key=lambda item: (-item["relevance_score"], item["source"], item["title"], item["id"]))
    return records


def _first_with_label(
    fallbacks: list[str],
    fallback_name: str,
    *candidates: tuple[Any, str],
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(fallback_name)
            return text
    fallbacks.append(fallback_name)
    return ""


def _first_text(*values: Any) -> str:
    for item in values:
        for value in _string_list(item):
            if value.strip():
                return value.strip()
    return ""


def _field_values(records: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for record in records:
        values.extend(_string_list(record.get(field)))
    return values


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in sorted(value.items()) if item not in (None, "")]
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return values
    return [str(value)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = " ".join(value.split()).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_fallback(context: dict[str, Any], field: str) -> bool:
    return field in set(context.get("fallbacks_used") or [])


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) or "none"


def _filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "design-brief"
