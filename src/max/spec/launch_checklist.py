"""Generate launch checklists from approved buildable ideas."""

from __future__ import annotations

from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


LAUNCH_CHECKLIST_SCHEMA_VERSION = "max-launch-checklist/v1"


def generate_launch_checklist(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an idea, evaluation, and tact spec into a deterministic launch checklist."""
    spec = tact_spec or generate_spec_preview(unit, evaluation)
    sections = _sections(unit, evaluation, spec)

    return {
        "schema_version": LAUNCH_CHECKLIST_SCHEMA_VERSION,
        "kind": "max.launch_checklist",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": unit.title,
            "one_liner": unit.one_liner,
            "target_user": unit.specific_user or unit.target_users,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
            "launch_gate": _launch_gate(unit, evaluation),
        },
        "sections": sections,
        "checklist_items": _flatten_items(sections),
        "risks": _risk_summary(unit, evaluation),
    }


def render_launch_checklist_markdown(checklist: dict[str, Any]) -> str:
    """Render a generated launch checklist as a markdown handoff document."""
    summary = checklist.get("summary", {})
    source = checklist.get("source", {})

    lines = [
        f"# {_text(summary.get('title')) or checklist.get('idea_id', 'Launch Checklist')} Launch Checklist",
        "",
        f"- Schema version: {_text(checklist.get('schema_version'))}",
        f"- Idea ID: {_text(checklist.get('idea_id'))}",
        f"- Source status: {_text(source.get('status'))}",
        f"- Launch gate: {_text(summary.get('launch_gate'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        "",
    ]

    one_liner = _text(summary.get("one_liner"))
    if one_liner:
        lines.extend([one_liner, ""])

    for section in checklist.get("sections", []):
        lines.extend([f"## {_text(section.get('title'))}", ""])
        description = _text(section.get("description"))
        if description:
            lines.extend([description, ""])
        for item in section.get("items", []):
            label = _text(item.get("id"))
            task = _text(item.get("task"))
            heading = f"### {label}: {task}" if label else f"### {task}"
            lines.extend(
                [
                    heading,
                    "",
                    f"- Status: {_text(item.get('status'))}",
                    f"- Owner: {_text(item.get('owner'))}",
                    f"- Required: {_text(item.get('required'))}",
                    f"- Rationale: {_text(item.get('rationale'))}",
                    f"- Evidence: {_text(item.get('evidence'))}",
                    "",
                ]
            )

    lines.extend(["## Risks", ""])
    risks = checklist.get("risks") or []
    if risks:
        for risk in risks:
            lines.append(
                f"- [{_text(risk.get('source'))}] {_text(risk.get('description'))} "
                f"Mitigation: {_text(risk.get('mitigation'))}"
            )
    else:
        lines.append("No risks were listed.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _sections(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    item_id = 1

    def items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal item_id
        rendered = []
        for raw in raw_items:
            rendered.append({"id": f"LC{item_id}", "status": "pending", **raw})
            item_id += 1
        return rendered

    return [
        {
            "id": "repository_setup",
            "title": "Repository Setup",
            "description": "Prepare the repository so the approved idea can be built and handed off.",
            "items": items(_repository_setup_items(unit, spec)),
        },
        {
            "id": "mvp_validation",
            "title": "MVP Validation",
            "description": "Prove the MVP scope solves the named workflow with representative users or fixtures.",
            "items": items(_mvp_validation_items(unit, spec)),
        },
        {
            "id": "release_readiness",
            "title": "Release Readiness",
            "description": "Make the first release installable, documented, and recoverable.",
            "items": items(_release_readiness_items(unit)),
        },
        {
            "id": "telemetry",
            "title": "Telemetry",
            "description": "Capture the minimum usage and failure signals needed after launch.",
            "items": items(_telemetry_items(unit, evaluation)),
        },
        {
            "id": "risk_review",
            "title": "Risk Review",
            "description": "Close or explicitly accept product, technical, and evaluation risks.",
            "items": items(_risk_review_items(unit, evaluation)),
        },
        {
            "id": "feedback_capture",
            "title": "Feedback Capture",
            "description": "Create the loop for post-launch customer evidence and Max feedback outcomes.",
            "items": items(_feedback_capture_items(unit)),
        },
    ]


def _repository_setup_items(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    stack = _stack_label(spec)
    return [
        _item(
            "Confirm package manager, runtime, and repository conventions before adding files.",
            f"Suggested stack: {stack}.",
            "Documented setup command or explicit deviation from suggested stack.",
        ),
        _item(
            "Create the minimal project structure for the MVP implementation and tests.",
            "The launch checklist should map cleanly onto repository files for autonomous handoff.",
            "Initial source, test, and documentation paths exist.",
        ),
        _item(
            "Add local configuration examples for required services, credentials, and environment variables.",
            unit.tech_approach or "Technical approach is not yet specific.",
            "Example config is committed without secrets.",
        ),
    ]


def _mvp_validation_items(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    scope = spec.get("execution", {}).get("mvp_scope") or [unit.solution]
    scope_text = "; ".join(_compact(item) for item in scope if _compact(item)) or unit.title
    validation_plan = _compact(spec.get("execution", {}).get("validation_plan")) or _compact(unit.validation_plan)
    return [
        _item(
            "Implement only the first MVP workflow and mark deferred scope as non-goals.",
            scope_text,
            "MVP scope is represented in tests or acceptance notes.",
        ),
        _item(
            "Run the MVP against representative fixture data or a real pilot workflow.",
            validation_plan or "No validation plan is attached yet.",
            "Validation notes include input, observed output, and launch decision.",
        ),
        _item(
            "Verify the target user can complete the workflow through the public interface.",
            unit.specific_user or unit.target_users,
            "Recorded CLI/API/UI result from the public entry point.",
        ),
    ]


def _release_readiness_items(unit: BuildableUnit) -> list[dict[str, Any]]:
    return [
        _item(
            "Document installation, configuration, usage, and known limits.",
            unit.one_liner,
            "README or release notes cover first-run path and constraints.",
        ),
        _item(
            "Run formatting, linting, type checks, and the repository test suite.",
            "Launch requires reproducible local validation.",
            "Passing command output or named blocker is attached to the handoff.",
        ),
        _item(
            "Prepare rollback or disablement instructions for the first launch.",
            "First releases need a fast recovery path.",
            "Rollback note identifies owner, trigger, and action.",
        ),
    ]


def _telemetry_items(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[dict[str, Any]]:
    telemetry_target = unit.workflow_context or "primary workflow"
    confidence_note = _lowest_confidence_note(evaluation)
    return [
        _item(
            "Track successful completions, user-visible failures, and latency for the primary workflow.",
            telemetry_target,
            "Telemetry events or logs are named and documented.",
        ),
        _item(
            "Add an adoption metric tied to the value proposition.",
            unit.value_proposition,
            "Metric definition includes numerator, denominator, and review cadence.",
        ),
        _item(
            "Capture evidence for the lowest-confidence evaluation assumption.",
            confidence_note,
            "Post-launch review has a concrete data source.",
        ),
    ]


def _risk_review_items(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[dict[str, Any]]:
    risks = _risk_summary(unit, evaluation)
    risk_text = "; ".join(risk["description"] for risk in risks) if risks else "No risks were listed."
    return [
        _item(
            "Review product, domain, security, compliance, and adoption risks before release.",
            risk_text,
            "Each risk is closed, mitigated, or explicitly accepted.",
        ),
        _item(
            "Convert launch-critical weaknesses into tests, monitors, or non-goals.",
            "; ".join(evaluation.weaknesses) if evaluation and evaluation.weaknesses else "No evaluation weaknesses recorded.",
            "Weakness handling is visible in release notes or validation artifacts.",
        ),
        _item(
            "Confirm the idea is approved for launch or record the remaining approval gate.",
            f"Current status: {unit.status}.",
            "Approval status and owner are recorded.",
        ),
    ]


def _feedback_capture_items(unit: BuildableUnit) -> list[dict[str, Any]]:
    first_customers = unit.first_10_customers or "first pilot users"
    return [
        _item(
            "Identify the first pilot users or customers and schedule feedback collection.",
            first_customers,
            "Pilot list includes contact, use case, and follow-up date.",
        ),
        _item(
            "Capture feedback outcomes in Max after launch.",
            "Use approved, rejected, published, or abandoned outcomes consistently.",
            "Feedback entry includes outcome, reason, and optional approval score.",
        ),
        _item(
            "Review launch evidence and decide whether to iterate, publish more broadly, or stop.",
            unit.validation_plan or "No validation plan is attached yet.",
            "Post-launch decision is linked to customer evidence.",
        ),
    ]


def _item(task: str, rationale: str, evidence: str) -> dict[str, Any]:
    return {
        "task": task,
        "rationale": _compact(rationale),
        "evidence": evidence,
        "owner": "launch_owner",
        "required": True,
    }


def _flatten_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for section in sections:
        for item in section["items"]:
            flattened.append(
                {
                    **item,
                    "section_id": section["id"],
                    "section_title": section["title"],
                }
            )
    return flattened


def _risk_summary(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> list[dict[str, str]]:
    risks = [
        {"source": "idea", "description": risk, "mitigation": "Resolve before broad launch or accept explicitly."}
        for risk in unit.domain_risks
    ]
    if evaluation:
        risks.extend(
            {
                "source": "evaluation",
                "description": weakness,
                "mitigation": "Convert into validation, telemetry, or a launch non-goal.",
            }
            for weakness in evaluation.weaknesses
        )
        if evaluation.recommendation not in {"strong_yes", "yes"}:
            risks.append(
                {
                    "source": "evaluation",
                    "description": f"Evaluation recommendation is {evaluation.recommendation}.",
                    "mitigation": "Resolve weaknesses before using this as a launch checklist.",
                }
            )
    else:
        risks.append(
            {
                "source": "evaluation",
                "description": "No utility evaluation is available.",
                "mitigation": "Run evaluation before launch review.",
            }
        )
    return risks


def _launch_gate(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> str:
    approved = unit.status in {"approved", "published"}
    recommended = evaluation is not None and evaluation.recommendation in {"strong_yes", "yes"}
    if approved and recommended:
        return "ready_for_launch_review"
    if approved:
        return "approved_needs_evaluation_review"
    return "needs_approval"


def _stack_label(spec: dict[str, Any]) -> str:
    stack = spec.get("solution", {}).get("suggested_stack") or {}
    values = [f"{key}={value}" for key, value in stack.items() if str(value).strip()]
    return ", ".join(values) if values else "unspecified"


def _lowest_confidence_note(evaluation: UtilityEvaluation | None) -> str:
    if evaluation is None:
        return "No evaluation is available."
    names = (
        "pain_severity",
        "addressable_scale",
        "build_effort",
        "composability",
        "competitive_density",
        "timing_fit",
        "compounding_value",
    )
    scores = [(name, getattr(evaluation, name)) for name in names]
    name, score = min(scores, key=lambda item: (item[1].confidence, item[0]))
    label = name.replace("_", " ")
    return f"{label}: confidence {score.confidence:.2f}; {score.reasoning}"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
