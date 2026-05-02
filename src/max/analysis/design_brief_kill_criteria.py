"""Deterministic kill criteria artifacts for BuildableUnit design briefs."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation

KIND = "max.design_brief.kill_criteria"
SCHEMA_VERSION = "max.design_brief.kill_criteria.v1"

_PASS_RECOMMENDATIONS = {"strong_yes", "yes"}
_FAIL_RECOMMENDATIONS = {"strong_no", "no"}
_PIVOT_RECOMMENDATIONS = {"maybe"}

_SEVERE_PROBLEM_TERMS = {
    "blocked",
    "blocker",
    "bottleneck",
    "costly",
    "delay",
    "error",
    "failure",
    "manual",
    "missed",
    "pain",
    "risk",
    "slow",
    "waste",
}
_COMPLIANCE_RISK_TERMS = {
    "audit",
    "compliance",
    "consent",
    "credential",
    "gdpr",
    "hipaa",
    "legal",
    "oauth",
    "permission",
    "pii",
    "privacy",
    "regulated",
    "security",
    "soc2",
}
_DEPENDENCY_TERMS = {
    "api",
    "connector",
    "dependency",
    "integration",
    "oauth",
    "platform",
    "third-party",
    "vendor",
    "webhook",
}
_CONTRADICTION_TERMS = {
    "contradict",
    "declined",
    "negative",
    "no demand",
    "not willing",
    "refute",
    "rejected",
    "weak demand",
}

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "criterion_type",
    "criterion_id",
    "category",
    "label",
    "status",
    "threshold",
    "evidence_backed_reason",
    "action",
    "source_reference_ids",
)


@dataclass(frozen=True)
class KillCriterion:
    """A single stop, pivot, or continue gate."""

    id: str
    category: str
    label: str
    status: str
    threshold: str
    evidence_backed_reason: str
    source_reference_ids: list[str]
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "label": self.label,
            "status": self.status,
            "threshold": self.threshold,
            "evidence_backed_reason": self.evidence_backed_reason,
            "source_reference_ids": self.source_reference_ids,
            "action": self.action,
        }


def build_design_brief_kill_criteria(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build stop, pivot, and continue gates for a design brief candidate."""
    evidence_refs = _evidence_references(unit, evidence or [])
    metrics = _metrics(unit, evaluation, evidence_refs)
    stop = _stop_criteria(unit, metrics)
    pivot = _pivot_criteria(unit, metrics)
    continue_ = _continue_criteria(unit, metrics)
    decision = _decision(stop, pivot, continue_)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "buildable_unit",
            "id": unit.id,
            "generated_at": unit.updated_at.isoformat() if unit.updated_at else None,
        },
        "design_brief": {
            "id": unit.id,
            "title": unit.title,
            "domain": unit.domain,
            "category": str(unit.category),
            "status": unit.status,
            "target_users": unit.target_users,
            "specific_user": unit.specific_user,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
        },
        "summary": {
            "decision": decision,
            "stop_trigger_count": len(stop),
            "pivot_trigger_count": len(pivot),
            "continue_signal_count": len(continue_),
            "evidence_count": metrics["evidence_count"],
            "evidence_source_diversity": metrics["evidence_source_diversity"],
            "contradictory_evidence_count": metrics["contradictory_evidence_count"],
            "problem_severity": metrics["problem_severity"],
            "evaluation_recommendation": metrics["evaluation_recommendation"],
            "dependency_risk": metrics["dependency_risk"],
            "compliance_security_risk": metrics["compliance_security_risk"],
            "target_user_clarity": metrics["target_user_clarity"],
        },
        "metrics": metrics,
        "stop_triggers": [criterion.to_dict() for criterion in stop],
        "pivot_triggers": [criterion.to_dict() for criterion in pivot],
        "continue_signals": [criterion.to_dict() for criterion in continue_],
        "next_validation_action": _next_validation_action(decision, unit, metrics, stop, pivot),
        "evidence_references": evidence_refs,
    }


def render_design_brief_kill_criteria(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render kill criteria as Markdown, deterministic JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported kill criteria format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Kill Criteria: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Design brief: `{brief['id']}`",
        f"Decision: {summary['decision']}",
        f"Evidence: {summary['evidence_count']} reference(s) across {summary['evidence_source_diversity']} source type(s)",
        f"Evaluation recommendation: {summary['evaluation_recommendation']}",
        "",
        "## Stop Triggers",
        "",
    ]
    _render_criteria(lines, report["stop_triggers"])
    lines.extend(["", "## Pivot Triggers", ""])
    _render_criteria(lines, report["pivot_triggers"])
    lines.extend(["", "## Continue Signals", ""])
    _render_criteria(lines, report["continue_signals"])
    action = report["next_validation_action"]
    lines.extend(
        [
            "",
            "## Next Validation Action",
            "",
            f"- Owner: {action['owner']}",
            f"- Action: {action['action']}",
            f"- Success condition: {action['success_condition']}",
            f"- Failure condition: {action['failure_condition']}",
            f"- Source references: {_inline_ids(action['source_reference_ids'])}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def kill_criteria_filename(design_brief: BuildableUnit | dict[str, Any], *, fmt: str = "markdown") -> str:
    """Return a stable filename for a kill criteria export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _get_field(design_brief, "id") or "design-brief"
    title = _get_field(design_brief, "title") or "kill-criteria"
    return f"{_filename_part(str(brief_id))}-{_filename_part(str(title))}-kill-criteria.{extension}"


def _stop_criteria(unit: BuildableUnit, metrics: dict[str, Any]) -> list[KillCriterion]:
    criteria: list[KillCriterion] = []
    if metrics["evidence_count"] == 0:
        criteria.append(
            _criterion(
                "DBKC-S1",
                "stop",
                "No evidence attached",
                "active",
                "Stop expansion when there are zero evidence references.",
                "The idea has no evidence references, so continued expansion would be speculative.",
                [],
                "Collect at least two independent evidence references before adding scope.",
            )
        )
    if metrics["evaluation_recommendation"] in _FAIL_RECOMMENDATIONS:
        criteria.append(
            _criterion(
                "DBKC-S2",
                "stop",
                "Negative evaluation recommendation",
                "active",
                "Stop when utility evaluation returns no or strong_no.",
                f"Utility evaluation recommendation is {metrics['evaluation_recommendation']}.",
                metrics["evaluation_reference_ids"],
                "Resolve evaluation weaknesses or retire the concept.",
            )
        )
    if metrics["problem_severity"] == "low" and metrics["evidence_count"] < 3:
        criteria.append(
            _criterion(
                "DBKC-S3",
                "stop",
                "Low severity without proof",
                "active",
                "Stop when the problem is low severity and has fewer than three evidence references.",
                "Problem language does not show urgent pain, and evidence is not strong enough to compensate.",
                metrics["all_reference_ids"],
                "Replace the problem statement with a validated high-severity workflow pain or reject the idea.",
            )
        )
    if metrics["target_user_clarity"] == "missing":
        criteria.append(
            _criterion(
                "DBKC-S4",
                "stop",
                "Missing target user",
                "active",
                "Stop when no specific user or concrete workflow is named.",
                "Target user and workflow context are missing, so validation cannot be assigned to a real audience.",
                metrics["all_reference_ids"],
                "Name the primary user, buyer, and workflow before continuing.",
            )
        )
    return criteria


def _pivot_criteria(unit: BuildableUnit, metrics: dict[str, Any]) -> list[KillCriterion]:
    criteria: list[KillCriterion] = []
    if metrics["contradictory_evidence_count"] > 0:
        criteria.append(
            _criterion(
                "DBKC-P1",
                "pivot",
                "Contradictory demand evidence",
                "active",
                "Pivot when evidence includes rejection, weak demand, or contradiction signals.",
                f"{metrics['contradictory_evidence_count']} evidence reference(s) contain negative or contradictory demand signals.",
                metrics["contradictory_reference_ids"],
                "Narrow the segment or switch to the workflow where evidence remains positive.",
            )
        )
    if metrics["evidence_count"] > 0 and metrics["evidence_source_diversity"] < 2:
        criteria.append(
            _criterion(
                "DBKC-P2",
                "pivot",
                "Single-source evidence",
                "active",
                "Pivot or hold scope when evidence comes from fewer than two source types.",
                "Evidence exists but is concentrated in one source type, increasing bias risk.",
                metrics["all_reference_ids"],
                "Collect a second source type before expanding the design brief.",
            )
        )
    if metrics["evaluation_recommendation"] in _PIVOT_RECOMMENDATIONS:
        criteria.append(
            _criterion(
                "DBKC-P3",
                "pivot",
                "Indeterminate evaluation recommendation",
                "active",
                "Pivot when utility evaluation remains maybe after evidence review.",
                "Utility evaluation is not a clear yes, so scope should stay constrained to the strongest claim.",
                metrics["evaluation_reference_ids"],
                "Run one validation test against the weakest evaluation dimension before implementation.",
            )
        )
    if metrics["dependency_risk"] == "high":
        criteria.append(
            _criterion(
                "DBKC-P4",
                "pivot",
                "High dependency risk",
                "active",
                "Pivot when the MVP depends on several vendors, integrations, APIs, or platform permissions.",
                "Technical approach and stack indicate multiple external dependencies.",
                metrics["all_reference_ids"],
                "Reduce the MVP to a fixture-backed or single-integration path.",
            )
        )
    if metrics["compliance_security_risk"] == "high":
        criteria.append(
            _criterion(
                "DBKC-P5",
                "pivot",
                "Compliance or security review required",
                "active",
                "Pivot when regulated, privacy, credential, or security risks are present before mitigation.",
                "Risk language references compliance, privacy, credentials, or security-sensitive handling.",
                metrics["all_reference_ids"],
                "Route the concept through legal, privacy, or security review and remove sensitive scope if unresolved.",
            )
        )
    if metrics["target_user_clarity"] == "broad":
        criteria.append(
            _criterion(
                "DBKC-P6",
                "pivot",
                "Broad target users",
                "active",
                "Pivot when target users are broad and no buyer context is attached.",
                "The target audience is broad enough that validation may average over incompatible workflows.",
                metrics["all_reference_ids"],
                "Pick one named persona and one workflow for the next validation pass.",
            )
        )
    return criteria


def _continue_criteria(unit: BuildableUnit, metrics: dict[str, Any]) -> list[KillCriterion]:
    criteria: list[KillCriterion] = []
    if metrics["problem_severity"] in {"medium", "high"}:
        criteria.append(
            _criterion(
                "DBKC-C1",
                "continue",
                "Meaningful problem severity",
                "satisfied",
                "Continue when the problem shows medium or high operational pain.",
                f"Problem severity is {metrics['problem_severity']} based on problem language and pain evaluation.",
                metrics["all_reference_ids"],
                "Keep validation centered on the severe workflow pain.",
            )
        )
    if metrics["evidence_count"] >= 3 and metrics["evidence_source_diversity"] >= 2:
        criteria.append(
            _criterion(
                "DBKC-C2",
                "continue",
                "Diverse evidence base",
                "satisfied",
                "Continue when there are at least three references across at least two source types.",
                f"Evidence includes {metrics['evidence_count']} references across {metrics['evidence_source_diversity']} source types.",
                metrics["all_reference_ids"],
                "Promote the strongest evidence-backed claim into the design brief validation plan.",
            )
        )
    if metrics["evaluation_recommendation"] in _PASS_RECOMMENDATIONS:
        criteria.append(
            _criterion(
                "DBKC-C3",
                "continue",
                "Positive utility evaluation",
                "satisfied",
                "Continue when recommendation is yes or strong_yes.",
                f"Utility evaluation recommendation is {metrics['evaluation_recommendation']}.",
                metrics["evaluation_reference_ids"],
                "Proceed to bounded MVP validation without expanding scope.",
            )
        )
    if metrics["target_user_clarity"] == "clear":
        criteria.append(
            _criterion(
                "DBKC-C4",
                "continue",
                "Clear target user and workflow",
                "satisfied",
                "Continue when a specific user and workflow context are named.",
                f"Primary user is {unit.specific_user or unit.target_users}; workflow is {unit.workflow_context or 'not specified'}.",
                metrics["all_reference_ids"],
                "Recruit validation participants matching the named user and workflow.",
            )
        )
    if metrics["dependency_risk"] != "high" and metrics["compliance_security_risk"] != "high":
        criteria.append(
            _criterion(
                "DBKC-C5",
                "continue",
                "No launch-blocking risk detected",
                "satisfied",
                "Continue when dependency and compliance/security risks are not high.",
                "Dependencies and compliance/security language do not indicate an immediate launch blocker.",
                metrics["all_reference_ids"],
                "Keep dependency and risk review in the validation checklist.",
            )
        )
    return criteria


def _metrics(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | dict[str, Any] | None,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    recommendation = _evaluation_field(evaluation, "recommendation") or "not_run"
    pain_value = _dimension_value(evaluation, "pain_severity")
    all_text = " ".join(
        [
            unit.title,
            unit.one_liner,
            unit.problem,
            unit.solution,
            unit.value_proposition,
            unit.workflow_context,
            unit.evidence_rationale,
            " ".join(unit.domain_risks),
        ]
    ).lower()
    source_types = {ref["source_type"] for ref in evidence_refs if ref.get("source_type")}
    contradictory_refs = [
        ref["id"]
        for ref in evidence_refs
        if _contains_any(f"{ref.get('summary', '')} {ref.get('polarity', '')}", _CONTRADICTION_TERMS)
        or str(ref.get("polarity", "")).lower() in {"negative", "contradictory"}
    ]
    dependency_text = " ".join(
        [
            unit.tech_approach,
            unit.composability_notes,
            " ".join(str(value) for value in unit.suggested_stack.values()),
        ]
    ).lower()
    dependency_hits = _term_hits(dependency_text, _DEPENDENCY_TERMS)
    compliance_hits = _term_hits(all_text, _COMPLIANCE_RISK_TERMS)
    evidence_ids = [ref["id"] for ref in evidence_refs]
    evaluation_ids = ["evaluation"] if recommendation != "not_run" else []

    return {
        "evidence_count": len(evidence_refs),
        "evidence_source_diversity": len(source_types),
        "evidence_source_types": sorted(source_types),
        "contradictory_evidence_count": len(contradictory_refs),
        "contradictory_reference_ids": contradictory_refs,
        "problem_severity": _problem_severity(unit, pain_value),
        "evaluation_recommendation": str(recommendation),
        "evaluation_overall_score": _evaluation_field(evaluation, "overall_score"),
        "dependency_risk": "high" if len(dependency_hits) >= 3 else "medium" if dependency_hits else "low",
        "dependency_terms": dependency_hits,
        "compliance_security_risk": "high" if compliance_hits else "low",
        "compliance_security_terms": compliance_hits,
        "target_user_clarity": _target_user_clarity(unit),
        "all_reference_ids": evidence_ids,
        "evaluation_reference_ids": evaluation_ids,
    }


def _evidence_references(
    unit: BuildableUnit,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for index, item in enumerate(evidence, start=1):
        ref_id = str(item.get("id") or item.get("signal_id") or item.get("insight_id") or f"evidence-{index}")
        refs.append(
            {
                "id": ref_id,
                "source_type": str(item.get("source_type") or item.get("type") or item.get("source") or "external"),
                "summary": str(item.get("summary") or item.get("title") or item.get("content") or ref_id),
                "polarity": str(item.get("polarity") or item.get("sentiment") or ""),
                "url": str(item.get("url") or ""),
            }
        )
    refs.extend(_refs_from_ids(unit.inspiring_insights, "insight"))
    refs.extend(_refs_from_ids(unit.evidence_signals, "signal"))
    refs.extend(_refs_from_ids(unit.source_idea_ids, "source_idea"))
    if unit.evidence_rationale.strip():
        refs.append(
            {
                "id": "evidence-rationale",
                "source_type": "rationale",
                "summary": unit.evidence_rationale.strip(),
                "polarity": "",
                "url": "",
            }
        )
    return _dedupe_refs(refs)


def _refs_from_ids(values: list[str], source_type: str) -> list[dict[str, str]]:
    return [
        {"id": str(value), "source_type": source_type, "summary": str(value), "polarity": "", "url": ""}
        for value in values
        if str(value).strip()
    ]


def _decision(
    stop: list[KillCriterion],
    pivot: list[KillCriterion],
    continue_: list[KillCriterion],
) -> str:
    if stop:
        return "stop"
    if pivot:
        return "pivot"
    if len(continue_) >= 3:
        return "continue"
    return "validate_more"


def _next_validation_action(
    decision: str,
    unit: BuildableUnit,
    metrics: dict[str, Any],
    stop: list[KillCriterion],
    pivot: list[KillCriterion],
) -> dict[str, Any]:
    refs = (stop or pivot or [])[0].source_reference_ids if (stop or pivot) else metrics["all_reference_ids"]
    if decision == "stop":
        return {
            "owner": "product owner",
            "action": "Do not expand the design brief until the active stop trigger is resolved or the idea is retired.",
            "success_condition": "Stop trigger is removed by new evidence, clearer user scope, or a passing evaluation.",
            "failure_condition": "The same stop trigger remains after one focused evidence pass.",
            "source_reference_ids": refs,
        }
    if decision == "pivot":
        return {
            "owner": "research owner",
            "action": f"Run a focused validation pass for {unit.specific_user or unit.target_users} in {unit.workflow_context or 'the target workflow'}.",
            "success_condition": "At least two source types support the revised segment and no contradiction remains unresolved.",
            "failure_condition": "Evidence remains single-source, contradictory, or dependent on high-risk scope.",
            "source_reference_ids": refs,
        }
    return {
        "owner": "product owner",
        "action": "Proceed to bounded MVP validation while keeping the stop and pivot gates visible in the brief.",
        "success_condition": "Validation confirms the severe problem, target user, and willingness to adopt the MVP scope.",
        "failure_condition": "Validation creates a new stop or pivot trigger.",
        "source_reference_ids": metrics["all_reference_ids"],
    }


def _criterion(
    criterion_id: str,
    category: str,
    label: str,
    status: str,
    threshold: str,
    reason: str,
    refs: list[str],
    action: str,
) -> KillCriterion:
    return KillCriterion(
        id=criterion_id,
        category=category,
        label=label,
        status=status,
        threshold=threshold,
        evidence_backed_reason=reason,
        source_reference_ids=refs,
        action=action,
    )


def _problem_severity(unit: BuildableUnit, pain_value: float | None) -> str:
    if pain_value is not None:
        if pain_value >= 7.0:
            return "high"
        if pain_value >= 4.0:
            return "medium"
        return "low"
    text = f"{unit.problem} {unit.current_workaround} {unit.why_now}".lower()
    hits = _term_hits(text, _SEVERE_PROBLEM_TERMS)
    if len(hits) >= 2:
        return "high"
    if hits or len([word for word in unit.problem.split() if word]) >= 10:
        return "medium"
    return "low"


def _target_user_clarity(unit: BuildableUnit) -> str:
    if _meaningful(unit.specific_user, min_words=2) and _meaningful(unit.workflow_context, min_words=3):
        return "clear"
    if unit.target_users in {"humans", "agents"} and _meaningful(unit.workflow_context, min_words=3):
        return "clear"
    if not unit.specific_user and not unit.workflow_context:
        return "missing"
    return "broad"


def _dimension_value(evaluation: UtilityEvaluation | dict[str, Any] | None, name: str) -> float | None:
    dimension = _evaluation_field(evaluation, name)
    if isinstance(dimension, dict):
        value = dimension.get("value")
    else:
        value = getattr(dimension, "value", None)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluation_field(evaluation: UtilityEvaluation | dict[str, Any] | None, name: str) -> Any:
    if evaluation is None:
        return None
    if isinstance(evaluation, dict):
        return evaluation.get(name)
    return getattr(evaluation, name, None)


def _render_criteria(lines: list[str], criteria: list[dict[str, Any]]) -> None:
    if not criteria:
        lines.append("- None")
        return
    for criterion in criteria:
        lines.extend(
            [
                f"- **{criterion['id']} {criterion['label']}** ({criterion['status']})",
                f"  Threshold: {criterion['threshold']}",
                f"  Reason: {criterion['evidence_backed_reason']}",
                f"  Action: {criterion['action']}",
                f"  Source references: {_inline_ids(criterion['source_reference_ids'])}",
            ]
        )


def _render_csv(report: dict[str, Any]) -> str:
    brief = report["design_brief"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for criterion_type, group_name in (
        ("stop", "stop_triggers"),
        ("pivot", "pivot_triggers"),
        ("continue", "continue_signals"),
    ):
        for criterion in report[group_name]:
            writer.writerow(
                {
                    "design_brief_id": brief["id"],
                    "design_brief_title": brief["title"],
                    "criterion_type": criterion_type,
                    "criterion_id": criterion["id"],
                    "category": criterion["category"],
                    "label": criterion["label"],
                    "status": criterion["status"],
                    "threshold": criterion["threshold"],
                    "evidence_backed_reason": criterion["evidence_backed_reason"],
                    "action": criterion["action"],
                    "source_reference_ids": json.dumps(
                        criterion["source_reference_ids"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
    return output.getvalue()


def _term_hits(text: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if term in text)


def _contains_any(text: str, terms: set[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _meaningful(value: str | None, *, min_words: int) -> bool:
    if not value:
        return False
    words = [word for word in value.strip().split() if word]
    return len(words) >= min_words and len(value.strip()) >= 12


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        ref_id = str(ref.get("id") or "").strip()
        if not ref_id or ref_id in seen:
            continue
        seen.add(ref_id)
        deduped.append(ref)
    return deduped


def _get_field(design_brief: BuildableUnit | dict[str, Any], field: str) -> Any:
    if isinstance(design_brief, dict):
        return design_brief.get(field)
    return getattr(design_brief, field, None)


def _inline_ids(values: list[str]) -> str:
    return ", ".join(values) if values else "None"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    parts = [part for part in cleaned.replace("_", "-").split("-") if part]
    return "-".join(parts) or "design-brief"
