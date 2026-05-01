"""Generate deterministic rollback plans for implementation-ready specs."""

from __future__ import annotations

from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


ROLLBACK_PLAN_SCHEMA_VERSION = "max-rollback-plan/v1"


def generate_rollback_plan(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an idea, evaluation, and optional tact spec into rollback guidance."""
    spec = tact_spec or generate_spec_preview(unit, evaluation)

    return {
        "schema_version": ROLLBACK_PLAN_SCHEMA_VERSION,
        "kind": "max.rollback_plan",
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
            "evaluation_available": evaluation is not None,
        },
        "summary": {
            "title": unit.title,
            "target_user": unit.specific_user or unit.target_users,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
            "rollback_window": _rollback_window(unit),
        },
        "rollback_triggers": _rollback_triggers(unit, evaluation, spec),
        "reversible_migration_steps": _reversible_migration_steps(unit, spec),
        "data_backup_requirements": _data_backup_requirements(unit, spec),
        "monitoring_signals": _monitoring_signals(unit, evaluation, spec),
        "owner_roles": _owner_roles(unit),
        "go_no_go_checklist": _go_no_go_checklist(unit, evaluation),
    }


def render_rollback_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a rollback plan as a deterministic markdown handoff document."""
    summary = plan.get("summary", {})
    source = plan.get("source", {})

    lines = [
        f"# {_text(summary.get('title')) or _text(plan.get('idea_id')) or 'Idea'} Rollback Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Idea ID: {_text(plan.get('idea_id'))}",
        f"- Source status: {_text(source.get('status'))}",
        f"- Category: {_text(source.get('category'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Rollback window: {_text(summary.get('rollback_window'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    lines.extend(_section("Rollback Triggers", _trigger_lines(plan.get("rollback_triggers") or [])))
    lines.extend(_section("Reversible Migration Steps", _step_lines(plan.get("reversible_migration_steps") or [])))
    lines.extend(_section("Data Backup Requirements", _requirement_lines(plan.get("data_backup_requirements") or [])))
    lines.extend(_section("Monitoring Signals", _signal_lines(plan.get("monitoring_signals") or [])))
    lines.extend(_section("Owner Roles", _owner_lines(plan.get("owner_roles") or [])))
    lines.extend(_section("Go/No-Go Checklist", _checklist_lines(plan.get("go_no_go_checklist") or [])))

    return "\n".join(lines).rstrip() + "\n"


def _rollback_triggers(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    triggers = [
        _trigger(
            "trigger_validation_failure",
            "Representative validation fails",
            "Pilot or fixture validation cannot complete the target workflow.",
            "critical",
            _compact(spec.get("execution", {}).get("validation_plan")) or unit.validation_plan or "First workflow validation run.",
        ),
        _trigger(
            "trigger_data_integrity",
            "Data integrity regression",
            "New release corrupts, drops, duplicates, or misroutes user-visible data.",
            "critical",
            "Any confirmed data integrity defect after release.",
        ),
        _trigger(
            "trigger_operational_failure",
            "Operational failure rate exceeds launch tolerance",
            "Error, timeout, or failed job rate materially interrupts the MVP workflow.",
            "high",
            "Sustained failure rate above the team-defined launch threshold.",
        ),
        _trigger(
            "trigger_user_blocked",
            "Target user cannot complete the workflow",
            "The named user persona is blocked by the shipped interface, integration, or documentation.",
            "high",
            unit.specific_user or unit.target_users,
        ),
    ]

    if evaluation is None:
        triggers.append(
            _trigger(
                "trigger_missing_evaluation",
                "Utility evaluation is unavailable",
                "Rollback authority must stay conservative because no utility evaluation is attached.",
                "high",
                "Evaluation remains missing at launch approval time.",
            )
        )
    elif evaluation.recommendation in {"no", "strong_no"}:
        triggers.append(
            _trigger(
                "trigger_negative_recommendation",
                "Evaluation recommendation blocks launch",
                "Utility evaluation recommends against proceeding with the current release.",
                "critical",
                evaluation.recommendation,
            )
        )

    for index, risk in enumerate(unit.domain_risks[:3], start=1):
        if _compact(risk):
            triggers.append(
                _trigger(
                    f"trigger_domain_risk_{index}",
                    "Domain risk materializes",
                    risk,
                    "high",
                    "Domain owner confirms the risk affects the release path.",
                )
            )

    return triggers


def _reversible_migration_steps(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    stack = _stack_label(spec)
    return [
        _step(
            "step_1",
            "Freeze rollout",
            "Stop new exposure, queued jobs, scheduled automation, and promotion steps for the release.",
            "release_owner",
            "Rollout switch or deployment pipeline is paused.",
        ),
        _step(
            "step_2",
            "Restore previous executable version",
            f"Redeploy the last known-good build using the documented {stack} release path.",
            "technical_owner",
            "Public entry point resolves to the previous version.",
        ),
        _step(
            "step_3",
            "Reverse schema and configuration changes",
            "Apply only reversible migrations, feature flags, and configuration changes that were prepared before launch.",
            "technical_owner",
            "Schema, configuration, and environment values match the pre-release baseline.",
        ),
        _step(
            "step_4",
            "Replay or quarantine affected work",
            "Replay safe queued work from backup or quarantine affected records until integrity is verified.",
            "data_owner",
            "No unverified post-release records remain in the active workflow.",
        ),
        _step(
            "step_5",
            "Validate the restored workflow",
            unit.validation_plan or "Run the MVP validation plan against representative fixtures.",
            "qa_owner",
            "Target workflow passes through the public interface after rollback.",
        ),
    ]


def _data_backup_requirements(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = unit.workflow_context or "target workflow"
    return [
        _requirement(
            "backup_1",
            "Pre-release state snapshot",
            f"Capture database, file, queue, and configuration state for the {workflow}.",
            "before_launch",
            "data_owner",
        ),
        _requirement(
            "backup_2",
            "Migration rollback scripts",
            "Store forward and reverse migration commands with checksums or reviewed change identifiers.",
            "before_launch",
            "technical_owner",
        ),
        _requirement(
            "backup_3",
            "Post-release delta capture",
            "Track records, jobs, and external side effects created after launch so they can be replayed or quarantined.",
            "during_rollout",
            "data_owner",
        ),
        _requirement(
            "backup_4",
            "Configuration baseline",
            f"Record environment variables, integration settings, and suggested stack values: {_stack_label(spec)}.",
            "before_launch",
            "release_owner",
        ),
    ]


def _monitoring_signals(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    signals = [
        _signal(
            "monitor_1",
            "Workflow completion rate",
            f"Successful completion of {unit.workflow_context or 'the target workflow'} by {unit.specific_user or unit.target_users}.",
            "below agreed launch threshold",
            "release_owner",
        ),
        _signal(
            "monitor_2",
            "Error and timeout rate",
            "Application errors, CLI failures, failed jobs, and integration timeouts.",
            "sustained increase from pre-release baseline",
            "technical_owner",
        ),
        _signal(
            "monitor_3",
            "Data integrity checks",
            "Record counts, duplicate detection, failed writes, and reconciliation checks.",
            "any confirmed corruption or unreconciled mismatch",
            "data_owner",
        ),
        _signal(
            "monitor_4",
            "Validation fixture result",
            _compact(spec.get("execution", {}).get("validation_plan")) or unit.validation_plan or "Representative validation fixture.",
            "fixture fails after deployment",
            "qa_owner",
        ),
    ]
    if evaluation is None:
        signals.append(
            _signal(
                "monitor_5",
                "Evaluation availability",
                "Utility evaluation exists before widening rollout.",
                "missing evaluation at launch gate",
                "product_owner",
            )
        )
    return signals


def _owner_roles(unit: BuildableUnit) -> list[dict[str, Any]]:
    return [
        _owner("product_owner", unit.buyer or "buyer or sponsor", "Owns launch decision, rollback authority, and stakeholder communication."),
        _owner("release_owner", "release manager", "Coordinates rollout freeze, status updates, and go/no-go checklist completion."),
        _owner("technical_owner", "engineering owner", "Owns deployment rollback, reversible migrations, and runtime configuration."),
        _owner("data_owner", "data or operations owner", "Owns backups, delta capture, replay, quarantine, and integrity verification."),
        _owner("qa_owner", unit.specific_user or "validation owner", "Owns restored workflow validation and evidence capture."),
    ]


def _go_no_go_checklist(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[dict[str, Any]]:
    return [
        _check("check_1", "Previous deployable version is identified and accessible.", "technical_owner", True),
        _check("check_2", "Reverse migrations and configuration rollback steps are reviewed.", "technical_owner", True),
        _check("check_3", "Pre-release backup and post-release delta capture are verified.", "data_owner", True),
        _check("check_4", "Monitoring signals have owners and rollback thresholds.", "release_owner", True),
        _check("check_5", "Target workflow validation can be rerun after rollback.", "qa_owner", True),
        _check("check_6", "Stakeholder communication path is ready.", "product_owner", bool(unit.buyer)),
        _check("check_7", "Utility evaluation is present or explicitly waived.", "product_owner", evaluation is not None),
    ]


def _rollback_window(unit: BuildableUnit) -> str:
    if unit.category in {"automation", "integration", "application"}:
        return "first 24 hours after launch or until adoption stabilizes"
    return "first release cycle or until validation evidence is accepted"


def _stack_label(spec: dict[str, Any]) -> str:
    stack = spec.get("solution", {}).get("suggested_stack") or {}
    if isinstance(stack, dict) and stack:
        return ", ".join(f"{key}={value}" for key, value in sorted(stack.items()))
    return "documented runtime and package manager"


def _trigger(
    trigger_id: str,
    name: str,
    description: str,
    severity: str,
    threshold: str,
) -> dict[str, Any]:
    return {
        "id": trigger_id,
        "name": name,
        "description": description,
        "severity": severity,
        "threshold": threshold,
        "action": "freeze rollout and execute rollback steps",
    }


def _step(step_id: str, title: str, action: str, owner: str, verification: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "action": action,
        "owner": owner,
        "verification": verification,
    }


def _requirement(
    requirement_id: str,
    name: str,
    description: str,
    timing: str,
    owner: str,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "name": name,
        "description": description,
        "timing": timing,
        "owner": owner,
    }


def _signal(
    signal_id: str,
    name: str,
    description: str,
    rollback_threshold: str,
    owner: str,
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "name": name,
        "description": description,
        "rollback_threshold": rollback_threshold,
        "owner": owner,
    }


def _owner(role: str, assigned_to: str, responsibility: str) -> dict[str, Any]:
    return {
        "role": role,
        "assigned_to": assigned_to,
        "responsibility": responsibility,
    }


def _check(check_id: str, task: str, owner: str, required: bool) -> dict[str, Any]:
    return {
        "id": check_id,
        "task": task,
        "owner": owner,
        "required": required,
        "status": "pending",
    }


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _trigger_lines(triggers: list[dict[str, Any]]) -> list[str]:
    if not triggers:
        return ["No rollback triggers were listed."]
    lines: list[str] = []
    for trigger in triggers:
        lines.extend(
            [
                f"### {_text(trigger.get('id'))}: {_text(trigger.get('name'))}",
                "",
                f"- Severity: {_text(trigger.get('severity'))}",
                f"- Threshold: {_text(trigger.get('threshold'))}",
                f"- Action: {_text(trigger.get('action'))}",
                f"- Description: {_text(trigger.get('description'))}",
                "",
            ]
        )
    return lines


def _step_lines(steps: list[dict[str, Any]]) -> list[str]:
    if not steps:
        return ["No rollback steps were listed."]
    lines: list[str] = []
    for step in steps:
        lines.extend(
            [
                f"### {_text(step.get('id'))}: {_text(step.get('title'))}",
                "",
                f"- Owner: {_text(step.get('owner'))}",
                f"- Action: {_text(step.get('action'))}",
                f"- Verification: {_text(step.get('verification'))}",
                "",
            ]
        )
    return lines


def _requirement_lines(requirements: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {_text(item.get('id'))} [{_text(item.get('timing'))}; {_text(item.get('owner'))}]: "
        f"{_text(item.get('name'))} - {_text(item.get('description'))}"
        for item in requirements
    ] or ["No data backup requirements were listed."]


def _signal_lines(signals: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {_text(item.get('id'))} [{_text(item.get('owner'))}]: {_text(item.get('name'))} "
        f"rollback threshold: {_text(item.get('rollback_threshold'))}. {_text(item.get('description'))}"
        for item in signals
    ] or ["No monitoring signals were listed."]


def _owner_lines(owners: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {_text(item.get('role'))}: {_text(item.get('assigned_to'))} - {_text(item.get('responsibility'))}"
        for item in owners
    ] or ["No owner roles were listed."]


def _checklist_lines(checks: list[dict[str, Any]]) -> list[str]:
    return [
        f"- [{_text(item.get('status'))}] {_text(item.get('id'))} ({_text(item.get('owner'))}; "
        f"required={_text(item.get('required'))}): {_text(item.get('task'))}"
        for item in checks
    ] or ["No go/no-go checklist items were listed."]


def _compact(value: Any) -> str:
    return _text(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
