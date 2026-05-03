"""Generate deterministic risk registers for buildable ideas."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


RISK_REGISTER_SCHEMA_VERSION = "max-risk-register/v1"

DIMENSION_NAMES = (
    "pain_severity",
    "addressable_scale",
    "build_effort",
    "composability",
    "competitive_density",
    "timing_fit",
    "compounding_value",
)
LOW_DIMENSION_THRESHOLD = 6.0
LOW_CONFIDENCE_THRESHOLD = 0.5
WEAK_EVIDENCE_THRESHOLD = 50.0
STALE_EVIDENCE_DAYS = 180
RISK_REGISTER_CSV_COLUMNS = (
    "section",
    "row_type",
    "idea_id",
    "title",
    "key",
    "value",
    "priority",
    "risk_id",
    "severity",
    "likelihood",
    "source",
    "description",
    "owner_suggestion",
    "mitigations",
    "evidence_links",
    "validation_trigger",
)


def generate_risk_register(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    evidence_density: dict[str, Any] | None = None,
    contradictions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic risk register from one buildable idea and evidence."""
    risks = _domain_risks(unit)
    risks.extend(_missing_field_risks(unit))
    risks.extend(_evaluation_risks(evaluation))
    risks.extend(_evidence_risks(unit, evidence_density))
    risks.extend(_contradiction_risks(contradictions))

    risks = _prioritize(_dedupe_risks(risks))
    return {
        "schema_version": RISK_REGISTER_SCHEMA_VERSION,
        "kind": "max.risk_register",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "evaluation_available": evaluation is not None,
            "evidence_density_available": evidence_density is not None,
            "contradictions_available": contradictions is not None,
        },
        "summary": {
            "title": unit.title,
            "target_user": unit.specific_user or unit.target_users,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "risk_count": len(risks),
            "critical_risk_count": sum(1 for risk in risks if risk["severity"] == "critical"),
            "high_risk_count": sum(1 for risk in risks if risk["severity"] == "high"),
            "top_risk_id": risks[0]["id"] if risks else None,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
        },
        "risks": risks,
        "validation_triggers": [risk["validation_trigger"] for risk in risks],
    }


def render_risk_register_markdown(register: dict[str, Any]) -> str:
    """Render a generated risk register as a deterministic markdown handoff document."""
    summary = register.get("summary", {})
    source = register.get("source", {})

    lines = [
        f"# {_text(summary.get('title')) or _text(register.get('idea_id')) or 'Idea'} Risk Register",
        "",
        f"- Schema version: {_text(register.get('schema_version'))}",
        f"- Idea ID: {_text(register.get('idea_id'))}",
        f"- Source status: {_text(source.get('status'))}",
        f"- Domain: {_text(source.get('domain'))}",
        f"- Category: {_text(source.get('category'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
        "## Summary",
        "",
        f"- Risk count: {_text(summary.get('risk_count'))}",
        f"- Critical risks: {_text(summary.get('critical_risk_count'))}",
        f"- High risks: {_text(summary.get('high_risk_count'))}",
        f"- Top risk ID: {_text(summary.get('top_risk_id')) or 'none'}",
        "",
        "## Prioritized Risks",
        "",
    ]

    risks = register.get("risks") or []
    if risks:
        for risk in risks:
            lines.extend(
                [
                    f"### {risk.get('priority')}. {_text(risk.get('title'))}",
                    "",
                    f"- ID: {_text(risk.get('id'))}",
                    f"- Severity: {_text(risk.get('severity'))}",
                    f"- Likelihood: {_text(risk.get('likelihood'))}",
                    f"- Source: {_text(risk.get('source'))}",
                    f"- Description: {_text(risk.get('description'))}",
                    "- Evidence references:",
                    *_bullets(risk.get("evidence_links") or [], empty="None."),
                    "- Mitigations:",
                    *_bullets(risk.get("mitigations") or [], empty="None."),
                    f"- Owner suggestion: {_text(risk.get('owner_suggestion'))}",
                    f"- Validation trigger: {_text(risk.get('validation_trigger'))}",
                    "",
                ]
            )
    else:
        lines.extend(["No deterministic risks found.", ""])

    triggers = register.get("validation_triggers") or []
    lines.extend(
        [
            "## Validation Triggers",
            "",
            *_bullets(triggers, empty="None."),
            "",
            "## Source Flags",
            "",
            f"- Evaluation available: {_text(source.get('evaluation_available'))}",
            f"- Evidence density available: {_text(source.get('evidence_density_available'))}",
            f"- Contradictions available: {_text(source.get('contradictions_available'))}",
            "",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def render_risk_register_csv(register: dict[str, Any]) -> str:
    """Render a generated risk register as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(RISK_REGISTER_CSV_COLUMNS)
    for row in _csv_rows(register):
        writer.writerow([row[column] for column in RISK_REGISTER_CSV_COLUMNS])
    return output.getvalue()


def _domain_risks(unit: BuildableUnit) -> list[dict[str, Any]]:
    return [
        _risk(
            risk_id=f"domain_risk_{index}",
            title="Domain risk",
            description=risk,
            source="domain_risks",
            severity="high",
            likelihood="possible",
            evidence_links=_idea_evidence_links(unit),
            mitigations=[
                "Convert the risk into an explicit MVP non-goal, acceptance criterion, or launch gate.",
                "Review the risk with a domain-aware stakeholder before implementation starts.",
            ],
            owner_suggestion="product_owner",
            validation_trigger="Domain risk has an owner, mitigation, and accept-or-block decision before build handoff.",
        )
        for index, risk in enumerate(unit.domain_risks, start=1)
        if _compact(risk)
    ]


def _missing_field_risks(unit: BuildableUnit) -> list[dict[str, Any]]:
    fields = [
        (
            "missing_specific_user",
            "Missing specific user",
            unit.specific_user,
            "The idea has no specific user persona, so implementation choices may optimize for the wrong workflow.",
            "Name the first user persona and the job they are trying to complete.",
            "Persona and workflow are documented in the spec before implementation starts.",
        ),
        (
            "missing_buyer",
            "Missing buyer",
            unit.buyer,
            "The idea has no buyer or sponsor, so adoption and launch criteria are underspecified.",
            "Identify the economic buyer, internal sponsor, or adoption owner for the first release.",
            "Buyer or sponsor is named before launch checklist review.",
        ),
        (
            "missing_workflow_context",
            "Missing workflow context",
            unit.workflow_context,
            "The idea has no workflow context, making MVP boundaries and validation fixtures ambiguous.",
            "Describe where the product is invoked, what input it receives, and what output proves success.",
            "Workflow context is concrete enough to create one end-to-end acceptance test.",
        ),
    ]
    return [
        _risk(
            risk_id=risk_id,
            title=title,
            description=description,
            source="idea_fields",
            severity="high",
            likelihood="likely",
            evidence_links=[],
            mitigations=[mitigation],
            owner_suggestion="product_owner",
            validation_trigger=trigger,
        )
        for risk_id, title, value, description, mitigation, trigger in fields
        if not _compact(value)
    ]


def _evaluation_risks(evaluation: UtilityEvaluation | None) -> list[dict[str, Any]]:
    if evaluation is None:
        return [
            _risk(
                risk_id="missing_evaluation",
                title="Missing utility evaluation",
                description="No utility evaluation is available, so score-based build risk has not been assessed.",
                source="evaluation",
                severity="high",
                likelihood="possible",
                evidence_links=[],
                mitigations=["Run deterministic utility evaluation before treating this idea as build-ready."],
                owner_suggestion="evaluation_owner",
                validation_trigger="Utility evaluation exists and recommendation is reviewed.",
            )
        ]

    risks: list[dict[str, Any]] = []
    for name in DIMENSION_NAMES:
        score = getattr(evaluation, name)
        if score.value >= LOW_DIMENSION_THRESHOLD:
            continue
        label = name.replace("_", " ")
        risks.append(
            _risk(
                risk_id=f"low_{name}",
                title=f"Low {label} score",
                description=(
                    f"{label} scored {score.value:.1f}/10 with confidence "
                    f"{score.confidence:.2f}: {_compact(score.reasoning)}"
                ),
                source="evaluation_dimension",
                severity=_dimension_severity(score.value),
                likelihood=_confidence_likelihood(score.confidence),
                evidence_links=[],
                mitigations=[_dimension_mitigation(name)],
                owner_suggestion=_dimension_owner(name),
                validation_trigger=f"{label} is rescored to at least {LOW_DIMENSION_THRESHOLD:.1f} or explicitly accepted.",
            )
        )

    for index, weakness in enumerate(evaluation.weaknesses, start=1):
        if not _compact(weakness):
            continue
        risks.append(
            _risk(
                risk_id=f"evaluation_weakness_{index}",
                title="Evaluation weakness",
                description=weakness,
                source="evaluation_weakness",
                severity="medium",
                likelihood="possible",
                evidence_links=[],
                mitigations=["Convert the weakness into a validation task, spike, metric, or explicit non-goal."],
                owner_suggestion="product_owner",
                validation_trigger="Evaluation weakness is mapped to validation evidence or deferred scope.",
            )
        )

    low_confidence = [
        (name, getattr(evaluation, name))
        for name in DIMENSION_NAMES
        if getattr(evaluation, name).confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    if low_confidence:
        names = ", ".join(name.replace("_", " ") for name, _score in low_confidence)
        risks.append(
            _risk(
                risk_id="low_evaluation_confidence",
                title="Low evaluation confidence",
                description=f"Evaluation confidence is weak for: {names}.",
                source="evaluation_confidence",
                severity="medium",
                likelihood="likely",
                evidence_links=[],
                mitigations=["Collect direct evidence for the lowest-confidence scoring assumptions."],
                owner_suggestion="research_owner",
                validation_trigger="Lowest-confidence dimension has fresh supporting evidence or an updated score.",
            )
        )

    if evaluation.recommendation not in {"strong_yes", "yes"}:
        risks.append(
            _risk(
                risk_id="non_passing_recommendation",
                title="Non-passing recommendation",
                description=f"Evaluation recommendation is {evaluation.recommendation}.",
                source="evaluation_recommendation",
                severity="high",
                likelihood="likely",
                evidence_links=[],
                mitigations=["Resolve score weaknesses before implementation or reduce MVP scope until recommendation improves."],
                owner_suggestion="product_owner",
                validation_trigger="Recommendation is yes or strong_yes, or the exception is explicitly approved.",
            )
        )

    return risks


def _evidence_risks(
    unit: BuildableUnit,
    evidence_density: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    links = _idea_evidence_links(unit)
    risks: list[dict[str, Any]] = []

    raw_evidence_count = len(unit.inspiring_insights) + len(unit.evidence_signals) + len(unit.source_idea_ids)
    if raw_evidence_count < 2:
        risks.append(
            _risk(
                risk_id="thin_evidence",
                title="Thin evidence",
                description="The idea has fewer than two attached evidence references.",
                source="idea_evidence",
                severity="high",
                likelihood="likely",
                evidence_links=links,
                mitigations=["Attach at least two independent evidence references before implementation planning."],
                owner_suggestion="research_owner",
                validation_trigger="At least two evidence references from independent sources are linked.",
            )
        )

    if evidence_density is None:
        return risks

    density_score = float(evidence_density.get("density_score") or 0.0)
    if density_score < WEAK_EVIDENCE_THRESHOLD:
        risks.append(
            _risk(
                risk_id="weak_evidence_density",
                title="Weak evidence density",
                description=f"Evidence density score is {density_score:.1f}/100.",
                source="evidence_density",
                severity="high" if density_score < 30.0 else "medium",
                likelihood="likely",
                evidence_links=links,
                mitigations=["Add credible, diverse, and directly relevant signals until evidence density clears the review threshold."],
                owner_suggestion="research_owner",
                validation_trigger=f"Evidence density is at least {WEAK_EVIDENCE_THRESHOLD:.1f}/100.",
            )
        )

    warnings = evidence_density.get("missing_evidence_warnings") or []
    if warnings:
        risks.append(
            _risk(
                risk_id="missing_evidence_references",
                title="Missing evidence references",
                description=" ".join(_compact(warning) for warning in warnings if _compact(warning)),
                source="evidence_density",
                severity="medium",
                likelihood="likely",
                evidence_links=links,
                mitigations=["Resolve missing insight or signal IDs, or remove stale references from the idea."],
                owner_suggestion="research_owner",
                validation_trigger="Evidence density report has no missing evidence warnings.",
            )
        )

    average_credibility = evidence_density.get("average_credibility")
    if average_credibility is not None and float(average_credibility) < 0.55:
        risks.append(
            _risk(
                risk_id="low_evidence_credibility",
                title="Low evidence credibility",
                description=f"Average evidence credibility is {float(average_credibility):.2f}.",
                source="evidence_density",
                severity="medium",
                likelihood="possible",
                evidence_links=links,
                mitigations=["Add higher-credibility sources or downgrade claims supported only by weak evidence."],
                owner_suggestion="research_owner",
                validation_trigger="Average evidence credibility is at least 0.55 or weak sources are explicitly accepted.",
            )
        )

    newest = _parse_datetime(evidence_density.get("newest_evidence_timestamp"))
    if newest is not None:
        age_days = (datetime.now(timezone.utc) - newest).days
        if age_days > STALE_EVIDENCE_DAYS:
            risks.append(
                _risk(
                    risk_id="stale_evidence",
                    title="Stale evidence",
                    description=f"Newest resolved evidence is {age_days} days old.",
                    source="evidence_density",
                    severity="medium",
                    likelihood="possible",
                    evidence_links=links,
                    mitigations=["Refresh evidence with recent signals before committing launch or implementation scope."],
                    owner_suggestion="research_owner",
                    validation_trigger=f"Newest evidence is no more than {STALE_EVIDENCE_DAYS} days old.",
                )
            )

    return risks


def _contradiction_risks(contradictions: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not contradictions:
        return []

    risks: list[dict[str, Any]] = []
    for index, contradiction in enumerate(contradictions.get("contradictions") or [], start=1):
        severity = _map_contradiction_severity(contradiction.get("severity"))
        claim = _compact(contradiction.get("claim")) or _compact(contradiction.get("group_key"))
        signal_ids = [str(value) for value in contradiction.get("involved_signal_ids") or []]
        risks.append(
            _risk(
                risk_id=f"contradiction_{index}",
                title="Contradictory evidence",
                description=(
                    _compact(contradiction.get("suggested_review_note"))
                    or f"Evidence contains a contradiction for claim: {claim}."
                ),
                source="contradictions",
                severity=severity,
                likelihood="likely",
                evidence_links=signal_ids,
                mitigations=[
                    "Review the conflicting signals and split, reword, or downgrade the affected claim.",
                    "Do not use the contradicted claim as a launch-critical assumption until reviewed.",
                ],
                owner_suggestion="research_owner",
                validation_trigger="Contradiction summary is reviewed and the affected claim is resolved or accepted.",
            )
        )
    return risks


def _risk(
    *,
    risk_id: str,
    title: str,
    description: str,
    source: str,
    severity: str,
    likelihood: str,
    evidence_links: list[str],
    mitigations: list[str],
    owner_suggestion: str,
    validation_trigger: str,
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "title": title,
        "description": _compact(description),
        "source": source,
        "severity": severity,
        "likelihood": likelihood,
        "priority": 0,
        "evidence_links": list(dict.fromkeys(link for link in evidence_links if _compact(link))),
        "mitigations": [mitigation for mitigation in mitigations if _compact(mitigation)],
        "owner_suggestion": owner_suggestion,
        "validation_trigger": validation_trigger,
    }


def _prioritize(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks.sort(
        key=lambda risk: (
            _severity_rank(risk["severity"]),
            _likelihood_rank(risk["likelihood"]),
            risk["source"],
            risk["id"],
        )
    )
    for priority, risk in enumerate(risks, start=1):
        risk["priority"] = priority
    return risks


def _dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for risk in risks:
        if risk["id"] not in deduped:
            deduped[risk["id"]] = risk
    return list(deduped.values())


def _csv_rows(register: dict[str, Any]) -> list[dict[str, str]]:
    summary = register.get("summary") if isinstance(register.get("summary"), dict) else {}
    source = register.get("source") if isinstance(register.get("source"), dict) else {}
    idea_id = register.get("idea_id") or source.get("idea_id")
    title = summary.get("title")
    rows: list[dict[str, str]] = []

    for key in (
        "schema_version",
        "kind",
        "risk_count",
        "critical_risk_count",
        "high_risk_count",
        "top_risk_id",
        "recommendation",
        "overall_score",
        "target_user",
        "buyer",
        "workflow_context",
    ):
        value = register.get(key) if key in {"schema_version", "kind"} else summary.get(key)
        if value is None and key not in summary and key not in register:
            continue
        rows.append(
            _csv_row(
                section="summary",
                row_type="summary",
                idea_id=idea_id,
                title=title,
                key=key,
                value=value,
            )
        )

    for key in (
        "system",
        "type",
        "idea_id",
        "status",
        "domain",
        "category",
        "evaluation_available",
        "evidence_density_available",
        "contradictions_available",
    ):
        if key not in source:
            continue
        rows.append(
            _csv_row(
                section="source_flags",
                row_type="source_flag",
                idea_id=idea_id,
                title=title,
                key=key,
                value=source.get(key),
            )
        )

    for risk in sorted(
        (risk for risk in register.get("risks") or [] if isinstance(risk, dict)),
        key=_risk_csv_sort_key,
    ):
        rows.append(
            _csv_row(
                section="risks",
                row_type="risk",
                idea_id=idea_id,
                title=risk.get("title"),
                priority=risk.get("priority"),
                risk_id=risk.get("id"),
                severity=risk.get("severity"),
                likelihood=risk.get("likelihood"),
                source=risk.get("source"),
                description=risk.get("description"),
                owner_suggestion=risk.get("owner_suggestion"),
                mitigations=risk.get("mitigations"),
                evidence_links=risk.get("evidence_links"),
                validation_trigger=risk.get("validation_trigger"),
            )
        )

    return rows


def _csv_row(**values: Any) -> dict[str, str]:
    return {column: _csv_text(values.get(column)) for column in RISK_REGISTER_CSV_COLUMNS}


def _risk_csv_sort_key(risk: dict[str, Any]) -> tuple[int, str]:
    try:
        priority = int(risk.get("priority"))
    except (TypeError, ValueError):
        priority = 999_999
    return priority, _csv_text(risk.get("id"))


def _idea_evidence_links(unit: BuildableUnit) -> list[str]:
    return [
        *[f"insight:{insight_id}" for insight_id in unit.inspiring_insights],
        *[f"signal:{signal_id}" for signal_id in unit.evidence_signals],
        *[f"idea:{idea_id}" for idea_id in unit.source_idea_ids],
    ]


def _dimension_severity(value: float) -> str:
    if value < 3.0:
        return "critical"
    if value < 5.0:
        return "high"
    return "medium"


def _confidence_likelihood(confidence: float) -> str:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return "possible"
    return "likely"


def _dimension_owner(name: str) -> str:
    if name in {"build_effort", "composability"}:
        return "engineering_owner"
    if name in {"addressable_scale", "competitive_density"}:
        return "go_to_market_owner"
    return "product_owner"


def _dimension_mitigation(name: str) -> str:
    mitigations = {
        "pain_severity": "Interview target users to verify the pain is urgent and frequent enough for the MVP.",
        "addressable_scale": "Narrow or expand the target segment until the reachable market is explicit.",
        "build_effort": "Run a technical spike and cut scope to the smallest independently useful workflow.",
        "composability": "Define integration boundaries and remove coupling that blocks reuse.",
        "competitive_density": "Map alternatives and identify a defensible wedge before building.",
        "timing_fit": "Refresh market timing evidence and identify the trigger that makes now viable.",
        "compounding_value": "Add retention, data, workflow, or network loops that make usage compound over time.",
    }
    return mitigations[name]


def _map_contradiction_severity(value: Any) -> str:
    if value == "high":
        return "critical"
    if value == "medium":
        return "high"
    return "medium"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _likelihood_rank(value: str) -> int:
    return {"likely": 0, "possible": 1, "unlikely": 2}.get(value, 3)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    text = _compact(value)
    return text or "none"


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    if isinstance(value, set):
        return "; ".join(_csv_text(item) for item in sorted(value, key=str) if _csv_text(item))
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}: {_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    return str(value)


def _bullets(values: list[Any], *, empty: str = "None.") -> list[str]:
    items = [f"- {_text(value)}" for value in values if _compact(value)]
    return items or [empty]
