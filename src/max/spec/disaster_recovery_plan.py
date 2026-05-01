"""Generate deterministic disaster recovery plans for TactSpec previews."""

from __future__ import annotations

from typing import Any


DISASTER_RECOVERY_PLAN_SCHEMA_VERSION = "max-disaster-recovery-plan/v1"


def generate_disaster_recovery_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into disaster recovery guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    workflow = _compact(project.get("workflow_context")) or "target workflow"
    target_user = _compact(project.get("specific_user") or project.get("target_users")) or "primary user"
    stack = _stack_label(solution.get("suggested_stack"))

    return {
        "schema_version": DISASTER_RECOVERY_PLAN_SCHEMA_VERSION,
        "kind": "max.disaster_recovery_plan",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "domain": source.get("domain"),
            "category": source.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": title,
            "workflow_context": workflow,
            "target_user": target_user,
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "stack": stack,
            "recovery_tier": _recovery_tier(evaluation),
            "recovery_time_objective": _recovery_time_objective(evaluation),
            "recovery_point_objective": _recovery_point_objective(spec),
        },
        "critical_capabilities": _critical_capabilities(workflow, target_user, execution),
        "backup_strategy": _backup_strategy(workflow, stack),
        "restore_sequence": _restore_sequence(workflow, stack),
        "validation_checks": _validation_checks(workflow, execution),
        "owner_roles": _owner_roles(),
        "gaps": _gaps(spec, execution),
    }


def render_disaster_recovery_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a disaster recovery plan as deterministic markdown."""
    summary = plan.get("summary", {})
    source = plan.get("source", {})
    title = _compact(summary.get("title")) or _compact(source.get("idea_id")) or "TactSpec"

    lines = [
        f"# {title} Disaster Recovery Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Recovery tier: {_text(summary.get('recovery_tier'))}",
        f"- RTO: {_text(summary.get('recovery_time_objective'))}",
        f"- RPO: {_text(summary.get('recovery_point_objective'))}",
        "",
    ]
    lines.extend(_section("Critical Capabilities", _item_lines(plan.get("critical_capabilities") or [])))
    lines.extend(_section("Backup Strategy", _item_lines(plan.get("backup_strategy") or [])))
    lines.extend(_section("Restore Sequence", _item_lines(plan.get("restore_sequence") or [])))
    lines.extend(_section("Validation Checks", _item_lines(plan.get("validation_checks") or [])))
    lines.extend(_section("Owner Roles", _owner_lines(plan.get("owner_roles") or [])))
    lines.extend(_section("Gaps", _gap_lines(plan.get("gaps") or [])))
    return "\n".join(lines).rstrip() + "\n"


def _critical_capabilities(
    workflow: str,
    target_user: str,
    execution: dict[str, Any],
) -> list[dict[str, str]]:
    validation = _compact(execution.get("validation_plan")) or f"{target_user} can complete {workflow}."
    return [
        _item("CAP1", "Primary workflow availability", f"Restore enough service for {validation}"),
        _item("CAP2", "Data integrity", "Preserve user-visible records, configuration, and audit history."),
        _item("CAP3", "Operator access", "Maintain emergency access to deploy, inspect logs, and run restore commands."),
    ]


def _backup_strategy(workflow: str, stack: str) -> list[dict[str, str]]:
    return [
        _item("BCK1", "State snapshot", f"Back up datastore, files, queues, and configuration for {workflow}."),
        _item("BCK2", "Executable recovery point", f"Keep the last known-good {stack} release artifact deployable."),
        _item("BCK3", "Secret and config escrow", "Store required secrets and environment values in a recoverable vault."),
    ]


def _restore_sequence(workflow: str, stack: str) -> list[dict[str, str]]:
    return [
        _item("RST1", "Declare recovery mode", "Assign incident commander and freeze non-essential changes."),
        _item("RST2", "Restore dependencies", "Confirm network, datastore, object storage, and third-party dependencies."),
        _item("RST3", "Restore application", f"Deploy the known-good {stack} artifact and apply required configuration."),
        _item("RST4", "Restore state", f"Recover data needed for {workflow} and quarantine uncertain deltas."),
        _item("RST5", "Resume traffic", "Reopen access gradually after validation checks pass."),
    ]


def _validation_checks(workflow: str, execution: dict[str, Any]) -> list[dict[str, str]]:
    validation = _compact(execution.get("validation_plan")) or f"Run a representative {workflow} smoke test."
    return [
        _item("VAL1", "Workflow smoke test", validation),
        _item("VAL2", "Data consistency check", "Compare restored records, counts, and audit events against backup manifests."),
        _item("VAL3", "Monitoring check", "Confirm health checks, error logs, and alert routing are working after restore."),
    ]


def _owner_roles() -> list[dict[str, str]]:
    return [
        {"role": "incident_commander", "responsibility": "Own recovery declaration, status, and coordination."},
        {"role": "technical_owner", "responsibility": "Restore application, infrastructure, and integrations."},
        {"role": "data_owner", "responsibility": "Validate backup, restore, quarantine, and replay decisions."},
        {"role": "product_owner", "responsibility": "Approve customer impact decisions and recovery completion."},
    ]


def _gaps(spec: dict[str, Any], execution: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not _compact(execution.get("validation_plan")):
        gaps.append(
            {
                "id": "GAP1",
                "category": "missing_validation_plan",
                "description": "No validation plan is attached for post-restore workflow checks.",
                "owner": "product_owner",
            }
        )
    if not spec.get("evaluation"):
        gaps.append(
            {
                "id": "GAP2",
                "category": "missing_evaluation",
                "description": "No utility evaluation is attached to calibrate recovery criticality.",
                "owner": "product_owner",
            }
        )
    return gaps


def _recovery_tier(evaluation: dict[str, Any]) -> str:
    score = evaluation.get("overall_score")
    if isinstance(score, int | float) and score >= 75:
        return "priority_restore"
    if isinstance(score, int | float) and score >= 50:
        return "standard_restore"
    return "limited_restore"


def _recovery_time_objective(evaluation: dict[str, Any]) -> str:
    return "4 hours" if _recovery_tier(evaluation) == "priority_restore" else "1 business day"


def _recovery_point_objective(spec: dict[str, Any]) -> str:
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    stack = solution.get("suggested_stack")
    if isinstance(stack, dict) and any("database" in str(key).lower() for key in stack):
        return "15 minutes"
    return "24 hours or last validated snapshot"


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        return ", ".join(f"{key}={value}" for key, value in sorted(stack.items()))
    return _compact(stack) or "documented deployment"


def _item(identifier: str, name: str, description: str) -> dict[str, str]:
    return {"id": identifier, "name": name, "description": description}


def _item_lines(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {_text(item.get('id'))}: {_text(item.get('name'))} - {_text(item.get('description'))}"
        for item in items
    ] or ["None."]


def _owner_lines(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {_text(item.get('role'))}: {_text(item.get('responsibility'))}"
        for item in items
    ] or ["None."]


def _gap_lines(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {_text(item.get('id'))} [{_text(item.get('owner'))}]: {_text(item.get('description'))}"
        for item in items
    ] or ["None."]


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _compact(value: Any) -> str:
    return _text(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
