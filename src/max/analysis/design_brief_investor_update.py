"""Deterministic investor updates for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.investor_update"
SCHEMA_VERSION = "max.design_brief.investor_update.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "update_section",
    "metric_name",
    "status_or_value",
    "narrative",
    "risks_blockers",
    "asks",
    "evidence_source_references",
    "source_idea_ids",
    "details",
)


def build_design_brief_investor_update(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a concise investor or executive update from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    evaluations = _evaluations(store, source_ideas)
    evidence_refs = _evidence_references(design_brief, source_ideas)
    confidence = _confidence(design_brief, source_idea_ids, evidence_refs, evaluations)
    traction = _traction_signals(design_brief, source_ideas, evaluations, evidence_refs)
    learnings = _learnings_since_last_review(design_brief, source_ideas)
    risks = _top_risks(design_brief, source_ideas, source_idea_ids)
    asks = _asks(design_brief, source_ideas, confidence, risks, evidence_refs)
    milestones = _next_milestones(design_brief, source_idea_ids)

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
            "buyer": _first_text(
                design_brief.get("buyer"),
                _field_values(source_ideas, "buyer"),
                default="TBD buyer",
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                _field_values(source_ideas, "workflow_context"),
                default="TBD workflow",
            ),
        },
        "summary": _summary(design_brief, confidence, traction, risks, asks),
        "traction_signals": traction,
        "learnings_since_last_review": learnings,
        "top_risks": risks,
        "asks": asks,
        "next_milestones": milestones,
        "confidence": confidence,
        "source_metadata": {
            "source_idea_count": len(source_idea_ids),
            "evidence_reference_count": len(evidence_refs),
            "evaluation_count": len(evaluations),
            "missing_source_idea_ids": [
                idea["id"] for idea in source_ideas if idea.get("missing")
            ],
        },
        "evidence_references": evidence_refs,
        "evaluations": evaluations,
        "source_ideas": source_ideas,
    }


def render_design_brief_investor_update(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render an investor update as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_investor_update_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported investor update format: {fmt}")

    brief = report["design_brief"]
    confidence = report["confidence"]
    lines = [
        f"# Investor Update: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Confidence: {confidence['level']} ({confidence['score']}/100)",
        "",
        "## Summary",
        "",
        report["summary"]["narrative"],
        "",
        "## Traction Signals",
        "",
    ]
    lines.extend(_render_items(report["traction_signals"], "signal"))
    lines.extend(["", "## Learnings Since Last Review", ""])
    lines.extend(_render_items(report["learnings_since_last_review"], "learning"))
    lines.extend(["", "## Top Risks", ""])
    for risk in report["top_risks"]:
        lines.append(
            f"- **{risk['priority']} {risk['category']}**: {risk['risk']} "
            f"Mitigation: {risk['mitigation']}"
        )
    lines.extend(["", "## Asks", ""])
    lines.extend(_render_items(report["asks"], "ask"))
    lines.extend(["", "## Next Milestones", ""])
    for milestone in report["next_milestones"]:
        lines.append(
            f"- **{milestone['id']} {milestone['milestone']}** "
            f"({milestone['target_window']}): {milestone['success_signal']}"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_investor_update_csv(report: dict[str, Any]) -> str:
    """Render investor update artifacts as deterministic CSV text."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def investor_update_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Return a stable filename for an investor update export."""
    extension = "json" if fmt == "json" else "csv" if fmt == "csv" else "md"
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Investor Update'))}-"
        f"investor-update.{extension}"
    )


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    summary = report.get("summary") or {}
    confidence = report.get("confidence") or {}
    design_brief = report.get("design_brief") or {}

    if summary:
        rows.append(
            _csv_row(
                report,
                update_section="summary",
                metric_name="summary",
                status_or_value=summary.get("confidence_level"),
                narrative=summary.get("narrative"),
                risks_blockers=summary.get("risk_count"),
                asks=summary.get("ask_count"),
                evidence_source_references=_evidence_reference_ids(report),
                source_idea_ids=design_brief.get("source_idea_ids"),
                details={
                    "readiness_score": summary.get("readiness_score"),
                    "buyer": summary.get("buyer"),
                    "traction_signal_count": summary.get("traction_signal_count"),
                },
            )
        )

    if confidence:
        rows.append(
            _csv_row(
                report,
                update_section="confidence",
                metric_name="update_confidence",
                status_or_value=confidence.get("level"),
                narrative=confidence.get("rationale"),
                evidence_source_references=_evidence_reference_ids(report),
                source_idea_ids=design_brief.get("source_idea_ids"),
                details={"score": confidence.get("score")},
            )
        )

    for signal in report.get("traction_signals") or []:
        rows.append(
            _csv_row(
                report,
                update_section="traction_signals",
                metric_name=signal.get("id"),
                status_or_value=signal.get("strength"),
                narrative=signal.get("signal"),
                evidence_source_references=signal.get("basis"),
                source_idea_ids=signal.get("source_idea_ids"),
            )
        )

    for learning in report.get("learnings_since_last_review") or []:
        rows.append(
            _csv_row(
                report,
                update_section="learnings_since_last_review",
                metric_name=learning.get("id"),
                status_or_value=learning.get("category"),
                narrative=learning.get("learning"),
                evidence_source_references=learning.get("basis"),
            )
        )

    for risk in report.get("top_risks") or []:
        rows.append(
            _csv_row(
                report,
                update_section="top_risks",
                metric_name=risk.get("id"),
                status_or_value=risk.get("priority"),
                narrative=risk.get("mitigation"),
                risks_blockers=risk.get("risk"),
                source_idea_ids=risk.get("source_idea_ids"),
                details={"category": risk.get("category")},
            )
        )

    for ask in report.get("asks") or []:
        rows.append(
            _csv_row(
                report,
                update_section="asks",
                metric_name=ask.get("id"),
                status_or_value=ask.get("owner"),
                narrative=ask.get("rationale"),
                asks=ask.get("ask"),
            )
        )

    for milestone in report.get("next_milestones") or []:
        rows.append(
            _csv_row(
                report,
                update_section="next_milestones",
                metric_name=milestone.get("id"),
                status_or_value=milestone.get("target_window"),
                narrative=milestone.get("success_signal"),
                asks=milestone.get("milestone"),
                source_idea_ids=milestone.get("source_idea_ids"),
            )
        )

    for reference in report.get("evidence_references") or []:
        rows.append(
            _csv_row(
                report,
                update_section="evidence_references",
                metric_name=reference.get("id"),
                status_or_value=reference.get("type"),
                narrative=reference.get("description"),
                evidence_source_references=reference.get("id"),
            )
        )

    return rows


def _csv_row(report: dict[str, Any], **values: Any) -> dict[str, str]:
    design_brief = report.get("design_brief") or {}
    row: dict[str, Any] = {
        "design_brief_id": design_brief.get("id"),
        "design_brief_title": design_brief.get("title"),
        "update_section": "",
        "metric_name": "",
        "status_or_value": "",
        "narrative": "",
        "risks_blockers": "",
        "asks": "",
        "evidence_source_references": "",
        "source_idea_ids": "",
        "details": "",
    }
    row.update(values)
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _evidence_reference_ids(report: dict[str, Any]) -> list[str]:
    return [str(item["id"]) for item in report.get("evidence_references") or [] if item.get("id")]


def _summary(
    design_brief: dict[str, Any],
    confidence: dict[str, Any],
    traction: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    asks: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    status = design_brief.get("design_status") or "unknown"
    title = _first_text(design_brief.get("title"), default="This design brief")
    buyer = _first_text(design_brief.get("buyer"), default="the accountable buyer")
    top_risk = risks[0]["risk"] if risks else "risk review remains open"
    primary_ask = asks[0]["ask"] if asks else "Confirm the next review decision."
    narrative = (
        f"{title} is {status} with readiness {readiness:.1f}/100 and "
        f"{confidence['level']} update confidence. The strongest signal is "
        f"{traction[0]['signal'] if traction else 'early qualitative evidence'}; "
        f"the main risk is {top_risk}. Current ask: {primary_ask}"
    )
    return {
        "narrative": narrative,
        "readiness_score": readiness,
        "confidence_level": confidence["level"],
        "buyer": buyer,
        "traction_signal_count": len(traction),
        "risk_count": len(risks),
        "ask_count": len(asks),
    }


def _traction_signals(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    evidence_refs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if readiness:
        signals.append(
            {
                "id": "readiness",
                "signal": f"Readiness score is {readiness:.1f}/100.",
                "strength": _strength_from_score(readiness),
                "basis": "design_brief.readiness_score",
                "source_idea_ids": _source_idea_ids_from_ideas(source_ideas),
            }
    )
    if evaluations:
        best = max(
            evaluations,
            key=lambda item: (item["overall_score"], item["buildable_unit_id"]),
        )
        signals.append(
            {
                "id": "evaluation",
                "signal": (
                    f"Best linked evaluation is {best['overall_score']:.1f}/100 "
                    f"with recommendation {best['recommendation']}."
                ),
                "strength": _strength_from_score(best["overall_score"]),
                "basis": f"{best['buildable_unit_id']}.evaluation",
                "source_idea_ids": [best["buildable_unit_id"]],
            }
        )
    customer_segment = _first_text(
        design_brief.get("first_10_customers"),
        _field_values(source_ideas, "first_10_customers"),
    )
    if customer_segment:
        signals.append(
            {
                "id": "customer-segment",
                "signal": f"Initial customer segment is identified: {customer_segment}.",
                "strength": "medium",
                "basis": "first_10_customers",
                "source_idea_ids": _source_idea_ids_from_ideas(source_ideas),
            }
        )
    if evidence_refs:
        signals.append(
            {
                "id": "evidence-coverage",
                "signal": f"{len(evidence_refs)} evidence reference(s) are linked to the update.",
                "strength": "high" if len(evidence_refs) >= 4 else "medium",
                "basis": "evidence_references",
                "source_idea_ids": _source_idea_ids_from_ideas(source_ideas),
            }
        )
    if not signals:
        signals.append(
            {
                "id": "early-stage",
                "signal": "Traction is not yet evidenced; treat this as an early-stage update.",
                "strength": "low",
                "basis": "fallback",
                "source_idea_ids": _source_idea_ids_from_ideas(source_ideas),
            }
        )
    return signals[:5]


def _learnings_since_last_review(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [
        (
            "synthesis",
            design_brief.get("synthesis_rationale"),
            "design_brief.synthesis_rationale",
        ),
        ("timing", design_brief.get("why_this_now"), "design_brief.why_this_now"),
        ("validation", design_brief.get("validation_plan"), "design_brief.validation_plan"),
    ]
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        idea_id = str(idea["id"])
        candidates.extend(
            [
                ("evidence", idea.get("evidence_rationale"), f"{idea_id}.evidence_rationale"),
                ("workaround", idea.get("current_workaround"), f"{idea_id}.current_workaround"),
                ("value", idea.get("value_proposition"), f"{idea_id}.value_proposition"),
            ]
        )

    learnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for category, text, basis in candidates:
        clean = _first_text(text)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        learnings.append(
            {
                "id": f"L{len(learnings) + 1}",
                "category": category,
                "learning": clean,
                "basis": basis,
            }
        )
        if len(learnings) == 4:
            break

    if not learnings:
        learnings.append(
            {
                "id": "L1",
                "category": "fallback",
                "learning": "No new learning has been captured since the last review.",
                "basis": "fallback",
            }
        )
    return learnings


def _top_risks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    raw_risks = [
        *_string_list(design_brief.get("risks")),
        *_field_values(source_ideas, "domain_risks"),
    ]
    risks: list[dict[str, Any]] = []
    for risk in _dedupe(raw_risks)[:4]:
        priority = _risk_priority(risk)
        risks.append(
            {
                "id": f"R{len(risks) + 1}",
                "category": _risk_category(risk),
                "priority": priority,
                "risk": risk.rstrip("."),
                "mitigation": _risk_mitigation(risk, design_brief),
                "source_idea_ids": source_idea_ids,
            }
        )
    if not risks:
        risks.append(
            {
                "id": "R1",
                "category": "evidence",
                "priority": "medium",
                "risk": "Risk profile is under-specified for an investor or executive review",
                "mitigation": (
                    "Add owner-reviewed product, evidence, and launch risks before approval."
                ),
                "source_idea_ids": source_idea_ids,
            }
        )
    return risks


def _asks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    confidence: dict[str, Any],
    risks: list[dict[str, Any]],
    evidence_refs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    buyer = _first_text(
        design_brief.get("buyer"),
        _field_values(source_ideas, "buyer"),
        default="accountable owner",
    )
    validation = _first_text(
        design_brief.get("validation_plan"),
        _field_values(source_ideas, "validation_plan"),
    )
    asks = [
        {
            "id": "A1",
            "ask": f"Confirm {buyer} as the sponsor for the next review decision.",
            "owner": buyer,
            "rationale": "Investor and executive updates need a clear decision owner.",
        }
    ]
    if validation:
        asks.append(
            {
                "id": "A2",
                "ask": f"Fund or unblock validation: {validation}",
                "owner": buyer,
                "rationale": "Validation is the next proof point for the update.",
            }
        )
    if confidence["level"] == "low" or len(evidence_refs) < 3:
        asks.append(
            {
                "id": f"A{len(asks) + 1}",
                "ask": (
                    "Attach at least three independent evidence references before scale review."
                ),
                "owner": buyer,
                "rationale": "Evidence coverage is thin for external-facing confidence.",
            }
        )
    if risks:
        asks.append(
            {
                "id": f"A{len(asks) + 1}",
                "ask": f"Resolve or accept the top risk: {risks[0]['risk']}.",
                "owner": buyer,
                "rationale": "Top risk disposition is required before broader commitment.",
            }
        )
    return asks[:4]


def _next_milestones(
    design_brief: dict[str, Any],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    raw = _string_list(design_brief.get("first_milestones"))
    if not raw:
        raw = [
            "Define validation success criteria",
            "Review investor update with the accountable owner",
            "Decide whether to continue, revise, or hold",
        ]
    milestones = []
    for index, milestone in enumerate(raw[:5], start=1):
        milestones.append(
            {
                "id": f"M{index}",
                "milestone": milestone.rstrip("."),
                "target_window": f"next {index * 2} week(s)",
                "success_signal": _milestone_success_signal(milestone),
                "source_idea_ids": source_idea_ids,
            }
        )
    return milestones


def _confidence(
    design_brief: dict[str, Any],
    source_idea_ids: list[str],
    evidence_refs: list[dict[str, str]],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    score = min(35, len(evidence_refs) * 7)
    score += min(20, len(source_idea_ids) * 8)
    score += min(20, len(evaluations) * 10)
    score += round(readiness * 0.25)
    score = min(100, max(10, int(score)))
    if score >= 75:
        level = "high"
    elif score >= 50:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "score": score,
        "rationale": (
            f"Based on readiness {readiness:.1f}, {len(evidence_refs)} evidence reference(s), "
            f"{len(source_idea_ids)} source idea(s), and {len(evaluations)} evaluation(s)."
        ),
    }


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for field in ("validation_plan", "synthesis_rationale", "why_this_now"):
        value = _first_text(design_brief.get(field))
        if value:
            references.append(
                {"id": f"design_brief.{field}", "type": field, "description": value}
            )
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        idea_id = str(idea["id"])
        rationale = _first_text(idea.get("evidence_rationale"))
        if rationale:
            references.append(
                {
                    "id": f"{idea_id}.evidence_rationale",
                    "type": "source_idea_rationale",
                    "description": rationale,
                }
            )
        for signal_id in _string_list(idea.get("evidence_signals")):
            references.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "description": f"Linked evidence signal from source idea {idea_id}.",
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            references.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "description": f"Linked insight from source idea {idea_id}.",
                }
            )
    return _dedupe_references(references)


def _evaluations(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        evaluation = store.get_evaluation(str(idea["id"]))
        if not evaluation:
            continue
        data = evaluation.model_dump(mode="json")
        evaluations.append(
            {
                "buildable_unit_id": data["buildable_unit_id"],
                "overall_score": float(data.get("overall_score") or 0.0),
                "recommendation": data.get("recommendation") or "",
            }
        )
    return evaluations


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


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        for item in _string_list(value):
            if item:
                return item
    return default


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _dedupe_references(references: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in references:
        item_id = item["id"]
        if item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _source_idea_ids_from_ideas(source_ideas: list[dict[str, Any]]) -> list[str]:
    return [str(idea["id"]) for idea in source_ideas if not idea.get("missing")]


def _strength_from_score(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _risk_priority(risk: str) -> str:
    text = risk.lower()
    if any(term in text for term in ("legal", "security", "compliance", "revenue", "block")):
        return "high"
    if any(term in text for term in ("may", "might", "unclear", "unvalidated")):
        return "medium"
    return "medium"


def _risk_category(risk: str) -> str:
    text = risk.lower()
    if any(term in text for term in ("legal", "security", "compliance")):
        return "compliance"
    if any(term in text for term in ("revenue", "budget", "market", "buyer")):
        return "commercial"
    if any(term in text for term in ("integration", "data", "api", "technical")):
        return "execution"
    return "product"


def _risk_mitigation(risk: str, design_brief: dict[str, Any]) -> str:
    validation = _first_text(design_brief.get("validation_plan"))
    if validation:
        return f"Use the validation plan to test this directly: {validation}"
    category = _risk_category(risk)
    if category == "commercial":
        return "Confirm buyer commitment and budget tolerance before build commitment."
    if category == "compliance":
        return "Route through legal, security, or compliance review before launch planning."
    if category == "execution":
        return "Prototype the riskiest integration path before committing delivery dates."
    return "Assign an owner and define an evidence threshold for this risk."


def _milestone_success_signal(milestone: str) -> str:
    text = milestone.lower()
    if any(term in text for term in ("markdown", "json", "export", "generate", "build")):
        return "Artifact is generated deterministically and reviewed by the owner."
    if any(term in text for term in ("pilot", "validation", "test", "review")):
        return "Validation result is recorded with a continue, revise, or hold decision."
    return "Milestone completion is documented in the next stakeholder update."


def _render_items(items: list[dict[str, Any]], field: str) -> list[str]:
    return [f"- **{item['id']}**: {item[field]}" for item in items]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple | set):
        return "; ".join(_string_list(value))
    if isinstance(value, dict):
        filtered = {key: item for key, item in value.items() if item not in (None, "", [], {})}
        if not filtered:
            return ""
        return json.dumps(filtered, sort_keys=True, separators=(",", ":"))
    return str(value)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "design-brief"
