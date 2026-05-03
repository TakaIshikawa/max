"""Generate deterministic disaster recovery plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


DISASTER_RECOVERY_PLAN_SCHEMA_VERSION = "max-disaster-recovery-plan/v1"
DISASTER_RECOVERY_PLAN_CSV_COLUMNS = (
    "section",
    "type",
    "field",
    "source_idea_id",
    "title",
    "item_id",
    "name",
    "category",
    "severity",
    "owner",
    "timing",
    "cadence",
    "channel",
    "recovery_time_objective",
    "recovery_point_objective",
    "critical_system",
    "scenario",
    "procedure",
    "step",
    "objective",
    "description",
    "verification",
    "derived_from",
)

_DEPENDENCY_TERMS = {
    "Datadog": ("datadog",),
    "GitHub": ("github", "github actions", "github-actions"),
    "GitLab": ("gitlab",),
    "OpenAI": ("openai", "llm", "model"),
    "Postgres": ("postgres", "postgresql"),
    "Redis": ("redis",),
    "Salesforce": ("salesforce",),
    "Sentry": ("sentry",),
    "Slack": ("slack",),
    "Stripe": ("stripe",),
}

_STATE_TERMS = ("database", "datastore", "postgres", "redis", "storage", "bucket", "queue")
_CUSTOMER_DATA_TERMS = ("customer", "user data", "personal data", "pii", "email", "audit")


def generate_disaster_recovery_plan(unit_or_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a BuildableUnit-like or TactSpec-like dictionary into DR guidance."""
    spec = unit_or_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    title = _title(spec, source, project)
    workflow = _workflow(spec, project)
    target_user = _compact(project.get("specific_user") or project.get("target_users")) or "primary user"
    stack = solution.get("suggested_stack")
    stack_label = _stack_label(stack)
    dependencies = _critical_dependencies(spec, stack)
    evidence_references = _evidence_refs(spec)
    rto = _recovery_time_objective(evaluation)
    rpo = _recovery_point_objective(spec)

    return {
        "schema_version": DISASTER_RECOVERY_PLAN_SCHEMA_VERSION,
        "kind": "max.disaster_recovery_plan",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id") or spec.get("id"),
            "status": source.get("status") or spec.get("status"),
            "domain": source.get("domain") or spec.get("domain"),
            "category": source.get("category") or spec.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(evidence_references),
        },
        "summary": {
            "title": title,
            "workflow_context": workflow,
            "target_user": target_user,
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "stack": stack_label,
            "recovery_tier": _recovery_tier(evaluation),
            "recovery_time_objective": rto,
            "recovery_point_objective": rpo,
            "dependency_count": len(dependencies),
            "validation_drill_count": 3,
        },
        "recovery_objectives": _recovery_objectives(workflow, rto, rpo),
        "critical_capabilities": _critical_capabilities(workflow, target_user, execution),
        "critical_dependencies": dependencies,
        "backup_restore_assumptions": _backup_restore_assumptions(spec, workflow, stack_label),
        "backup_strategy": _backup_strategy(workflow, stack_label),
        "failover_steps": _failover_steps(workflow, dependencies),
        "restore_sequence": _restore_sequence(workflow, stack_label),
        "data_integrity_checks": _data_integrity_checks(workflow),
        "validation_checks": _validation_checks(workflow, execution),
        "communications": _communications(workflow),
        "owner_roles": _owner_roles(),
        "validation_drills": _validation_drills(workflow),
        "evidence_references": evidence_references,
        "gaps": _gaps(spec, execution, evidence_references),
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
        f"- Evidence references: {_text(source.get('evidence_reference_count') or len(plan.get('evidence_references') or []))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Recovery tier: {_text(summary.get('recovery_tier'))}",
        f"- RTO: {_text(summary.get('recovery_time_objective'))}",
        f"- RPO: {_text(summary.get('recovery_point_objective'))}",
        "",
    ]
    _extend_section(lines, "Recovery Objectives", plan.get("recovery_objectives") or [], _render_item)
    _extend_section(lines, "Critical Capabilities", plan.get("critical_capabilities") or [], _render_item)
    _extend_section(lines, "Critical Dependencies", plan.get("critical_dependencies") or [], _render_dependency)
    _extend_section(
        lines,
        "Backup and Restore Assumptions",
        plan.get("backup_restore_assumptions") or [],
        _render_assumption,
    )
    _extend_section(lines, "Backup Strategy", plan.get("backup_strategy") or [], _render_item)
    _extend_section(lines, "Failover Steps", plan.get("failover_steps") or [], _render_task)
    _extend_section(lines, "Restore Sequence", plan.get("restore_sequence") or [], _render_task)
    _extend_section(
        lines, "Data Integrity Checks", plan.get("data_integrity_checks") or [], _render_task
    )
    _extend_section(lines, "Validation Checks", plan.get("validation_checks") or [], _render_task)
    _extend_section(lines, "Communications", plan.get("communications") or [], _render_communication)
    _extend_section(lines, "Owner Roles", plan.get("owner_roles") or [], _render_owner)
    _extend_section(lines, "Validation Drills", plan.get("validation_drills") or [], _render_drill)
    _extend_section(
        lines, "Evidence References", _reference_items(plan.get("evidence_references") or []), _render_ref
    )
    _extend_section(lines, "Gaps", plan.get("gaps") or [], _render_gap)
    return "\n".join(lines).rstrip() + "\n"


def render_disaster_recovery_plan_csv(plan: dict[str, Any]) -> str:
    """Render a generated disaster recovery plan as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output, fieldnames=DISASTER_RECOVERY_PLAN_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in _csv_rows(plan or {}):
        writer.writerow(row)
    return output.getvalue()


def _recovery_objectives(workflow: str, rto: str, rpo: str) -> list[dict[str, Any]]:
    return [
        _item(
            "OBJ1",
            "Restore primary workflow",
            f"Recover the {workflow} path within {rto}.",
            ["project.workflow_context", "summary.recovery_time_objective"],
        ),
        _item(
            "OBJ2",
            "Limit data loss",
            f"Recover user-visible state to within {rpo}.",
            ["solution.suggested_stack", "summary.recovery_point_objective"],
        ),
        _item(
            "OBJ3",
            "Preserve auditability",
            "Keep recovery decisions, quarantined records, and replay actions traceable.",
            ["execution.validation_plan", "evidence"],
        ),
    ]


def _critical_capabilities(
    workflow: str,
    target_user: str,
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    validation = _compact(execution.get("validation_plan")) or f"{target_user} can complete {workflow}."
    return [
        _item(
            "CAP1",
            "Primary workflow availability",
            f"Restore enough service for {validation}",
            ["project.workflow_context", "execution.validation_plan"],
        ),
        _item(
            "CAP2",
            "Data integrity",
            "Preserve user-visible records, configuration, and audit history.",
            ["solution.suggested_stack", "acceptance_criteria"],
        ),
        _item(
            "CAP3",
            "Operator access",
            "Maintain emergency access to deploy, inspect logs, and run restore commands.",
            ["owner_roles", "configuration"],
        ),
    ]


def _critical_dependencies(spec: dict[str, Any], stack: Any) -> list[dict[str, Any]]:
    text = _haystack(spec)
    dependencies: list[dict[str, Any]] = []
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            label = _compact(value) or _compact(key)
            if label:
                dependencies.append(
                    _dependency(
                        f"DEP{len(dependencies) + 1}",
                        label,
                        _dependency_role(key),
                        _dependency_recovery_note(key, label),
                        ["solution.suggested_stack"],
                    )
                )
    elif _compact(stack):
        dependencies.append(
            _dependency(
                "DEP1",
                _compact(stack),
                "runtime",
                "Redeploy the documented runtime before restoring traffic.",
                ["solution.suggested_stack"],
            )
        )

    known_names = {item["name"].lower() for item in dependencies}
    for name, terms in sorted(_DEPENDENCY_TERMS.items()):
        if name.lower() not in known_names and _contains_any(text, terms):
            dependencies.append(
                _dependency(
                    f"DEP{len(dependencies) + 1}",
                    name,
                    "external_service",
                    f"Confirm {name} availability, credentials, and replay limits before resuming integrations.",
                    ["project", "solution", "execution.risks"],
                )
            )
    if not dependencies:
        dependencies.append(
            _dependency(
                "DEP1",
                "documented deployment",
                "runtime",
                "Restore the service runtime, configuration, and deployment pipeline from the last known-good release.",
                ["solution.suggested_stack"],
            )
        )
    return dependencies


def _backup_restore_assumptions(spec: dict[str, Any], workflow: str, stack: str) -> list[dict[str, Any]]:
    text = _haystack(spec)
    stateful = _contains_any(text, _STATE_TERMS)
    customer_data = _contains_any(text, _CUSTOMER_DATA_TERMS)
    assumptions = [
        _assumption(
            "ASM1",
            "Release artifact",
            f"The last known-good {stack} release can be redeployed without rebuilding from an unavailable host.",
            "verify deployment artifact retention before launch",
            ["solution.suggested_stack"],
        ),
        _assumption(
            "ASM2",
            "Configuration escrow",
            "Required environment values and secrets are recoverable from managed configuration stores.",
            "verify break-glass access and secret rotation owner",
            ["owner_roles", "configuration"],
        ),
        _assumption(
            "ASM3",
            "Workflow fixture",
            f"A representative fixture exists to prove the restored {workflow} path works.",
            "derive fixture from validation plan or acceptance criteria",
            ["execution.validation_plan", "acceptance_criteria"],
        ),
    ]
    if stateful or customer_data:
        assumptions.append(
            _assumption(
                "ASM4",
                "State backup",
                "Database, object, queue, and audit records have restorable snapshots or replayable logs.",
                "confirm backup schedule, retention, and restore permissions",
                ["solution.suggested_stack", "project.workflow_context"],
            )
        )
    return assumptions


def _backup_strategy(workflow: str, stack: str) -> list[dict[str, Any]]:
    return [
        _item(
            "BCK1",
            "State snapshot",
            f"Back up datastore, files, queues, and configuration for {workflow}.",
            ["solution.suggested_stack", "project.workflow_context"],
        ),
        _item(
            "BCK2",
            "Executable recovery point",
            f"Keep the last known-good {stack} release artifact deployable.",
            ["deployment_pipeline", "solution.suggested_stack"],
        ),
        _item(
            "BCK3",
            "Secret and config escrow",
            "Store required secrets and environment values in a recoverable vault.",
            ["configuration", "owner_roles"],
        ),
    ]


def _failover_steps(workflow: str, dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primary_dependency = dependencies[0]["name"] if dependencies else "primary runtime"
    return [
        _task(
            "FOV1",
            "Declare failover",
            "incident_commander",
            "Open the recovery channel, freeze non-essential releases, and set customer-facing status.",
            ["communications", "owner_roles"],
        ),
        _task(
            "FOV2",
            "Shift to degraded mode",
            "technical_owner",
            f"Disable non-critical jobs and preserve the minimum {workflow} path while {primary_dependency} is restored.",
            ["critical_capabilities", "critical_dependencies"],
        ),
        _task(
            "FOV3",
            "Protect write paths",
            "data_owner",
            "Pause or queue writes that cannot be reconciled safely during recovery.",
            ["data_integrity_checks", "backup_restore_assumptions"],
        ),
    ]


def _restore_sequence(workflow: str, stack: str) -> list[dict[str, Any]]:
    return [
        _task(
            "RST1",
            "Declare recovery mode",
            "incident_commander",
            "Assign recovery owners, capture timeline, and freeze non-essential changes.",
            ["owner_roles", "communications"],
        ),
        _task(
            "RST2",
            "Restore dependencies",
            "technical_owner",
            "Confirm network, datastore, object storage, queue, and third-party dependencies.",
            ["critical_dependencies"],
        ),
        _task(
            "RST3",
            "Restore application",
            "technical_owner",
            f"Deploy the known-good {stack} artifact and apply required configuration.",
            ["backup_strategy", "solution.suggested_stack"],
        ),
        _task(
            "RST4",
            "Restore state",
            "data_owner",
            f"Recover data needed for {workflow} and quarantine uncertain deltas.",
            ["backup_restore_assumptions", "data_integrity_checks"],
        ),
        _task(
            "RST5",
            "Resume traffic",
            "incident_commander",
            "Reopen access gradually after validation checks pass and communications are ready.",
            ["validation_checks", "communications"],
        ),
    ]


def _data_integrity_checks(workflow: str) -> list[dict[str, Any]]:
    return [
        _task(
            "DAT1",
            "Manifest comparison",
            "data_owner",
            "Compare restored record counts, checksums, object manifests, and audit events against the selected backup.",
            ["backup_restore_assumptions"],
        ),
        _task(
            "DAT2",
            "Replay reconciliation",
            "data_owner",
            "Identify queued, duplicated, or partially applied writes before replaying them.",
            ["failover_steps"],
        ),
        _task(
            "DAT3",
            "Workflow sample review",
            "product_owner",
            f"Inspect representative restored outputs from the {workflow} path before declaring recovery complete.",
            ["project.workflow_context", "acceptance_criteria"],
        ),
    ]


def _validation_checks(workflow: str, execution: dict[str, Any]) -> list[dict[str, Any]]:
    validation = _compact(execution.get("validation_plan")) or f"Run a representative {workflow} smoke test."
    return [
        _task("VAL1", "Workflow smoke test", "qa_owner", validation, ["execution.validation_plan"]),
        _task(
            "VAL2",
            "Data consistency check",
            "data_owner",
            "Compare restored records, counts, and audit events against backup manifests.",
            ["data_integrity_checks"],
        ),
        _task(
            "VAL3",
            "Monitoring check",
            "technical_owner",
            "Confirm health checks, error logs, dashboards, and alert routing are working after restore.",
            ["observability", "incident_response_plan"],
        ),
    ]


def _communications(workflow: str) -> list[dict[str, Any]]:
    return [
        _communication(
            "COM1",
            "Recovery declared",
            "incident_commander",
            "internal_recovery_channel",
            f"Confirm scope, impact, RTO/RPO targets, and current {workflow} availability.",
            ["summary", "recovery_objectives"],
        ),
        _communication(
            "COM2",
            "Customer impact update",
            "product_owner",
            "customer_status_channel",
            "Publish impact, workaround, and next update time when users are affected.",
            ["project.target_users", "critical_capabilities"],
        ),
        _communication(
            "COM3",
            "Recovery complete",
            "incident_commander",
            "internal_and_customer_channels",
            "Share validation result, residual risk, and follow-up owner after traffic resumes.",
            ["validation_checks", "data_integrity_checks"],
        ),
    ]


def _owner_roles() -> list[dict[str, Any]]:
    return [
        {
            "id": "OWN1",
            "role": "incident_commander",
            "responsibility": "Own recovery declaration, status cadence, failover decision, and completion call.",
            "derived_from": ["communications", "restore_sequence"],
        },
        {
            "id": "OWN2",
            "role": "technical_owner",
            "responsibility": "Restore application, infrastructure, dependencies, configuration, and observability.",
            "derived_from": ["critical_dependencies", "backup_strategy"],
        },
        {
            "id": "OWN3",
            "role": "data_owner",
            "responsibility": "Validate backup choice, restore integrity, quarantine decisions, and replay plan.",
            "derived_from": ["backup_restore_assumptions", "data_integrity_checks"],
        },
        {
            "id": "OWN4",
            "role": "product_owner",
            "responsibility": "Approve user impact decisions, customer messaging, and recovery acceptance.",
            "derived_from": ["project.buyer", "communications"],
        },
        {
            "id": "OWN5",
            "role": "qa_owner",
            "responsibility": "Run post-restore smoke tests, validation fixtures, and drill acceptance checks.",
            "derived_from": ["execution.validation_plan", "validation_drills"],
        },
    ]


def _validation_drills(workflow: str) -> list[dict[str, Any]]:
    return [
        _drill(
            "DRL1",
            "Tabletop recovery review",
            "quarterly",
            "incident_commander",
            "Walk through failover, communication, and owner handoffs without touching production.",
            ["failover_steps", "communications", "owner_roles"],
        ),
        _drill(
            "DRL2",
            "Restore rehearsal",
            "quarterly",
            "technical_owner",
            "Restore the application and representative state into an isolated environment.",
            ["backup_strategy", "restore_sequence"],
        ),
        _drill(
            "DRL3",
            "Workflow validation drill",
            "before major launch",
            "qa_owner",
            f"Run the restored {workflow} fixture and record data integrity evidence.",
            ["validation_checks", "data_integrity_checks"],
        ),
    ]


def _gaps(
    spec: dict[str, Any], execution: dict[str, Any], evidence_references: list[dict[str, str]]
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not _compact(execution.get("validation_plan")):
        gaps.append(
            _gap(
                "GAP1",
                "missing_validation_plan",
                "No validation plan is attached for post-restore workflow checks.",
                "product_owner",
                ["execution.validation_plan"],
            )
        )
    if not isinstance(spec.get("evaluation"), dict):
        gaps.append(
            _gap(
                "GAP2",
                "missing_evaluation",
                "No utility evaluation is attached to calibrate recovery criticality.",
                "product_owner",
                ["evaluation"],
            )
        )
    if not _acceptance_criteria(spec):
        gaps.append(
            _gap(
                "GAP3",
                "missing_acceptance_criteria",
                "No acceptance criteria are attached to anchor recovery validation.",
                "qa_owner",
                ["acceptance_criteria"],
            )
        )
    if not evidence_references:
        gaps.append(
            _gap(
                "GAP4",
                "missing_evidence_references",
                "No source evidence references are available for recovery traceability.",
                "product_owner",
                ["evidence"],
            )
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
    tier = _recovery_tier(evaluation)
    if tier == "priority_restore":
        return "4 hours"
    if tier == "standard_restore":
        return "1 business day"
    return "2 business days"


def _recovery_point_objective(spec: dict[str, Any]) -> str:
    text = _haystack(spec)
    if _contains_any(text, ("realtime", "real-time", "payment", "transaction", "customer data")):
        return "15 minutes"
    if _contains_any(text, _STATE_TERMS):
        return "4 hours"
    return "24 hours or last validated snapshot"


def _title(spec: dict[str, Any], source: dict[str, Any], project: dict[str, Any]) -> str:
    return (
        _compact(project.get("title"))
        or _compact(spec.get("title"))
        or _compact(source.get("idea_id"))
        or _compact(spec.get("id"))
        or "Untitled TactSpec"
    )


def _workflow(spec: dict[str, Any], project: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _compact(spec.get("workflow_context"))
        or _compact(spec.get("problem"))
        or "primary workflow"
    )


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        return ", ".join(f"{key}={value}" for key, value in sorted(stack.items()))
    if isinstance(stack, dict):
        return "unspecified"
    return _compact(stack) or "unspecified"


def _dependency_role(key: Any) -> str:
    normalized = _compact(key).lower()
    if any(term in normalized for term in ("database", "db", "storage", "queue", "cache")):
        return "stateful_data"
    if any(term in normalized for term in ("observability", "monitor", "alert")):
        return "observability"
    if any(term in normalized for term in ("auth", "identity", "sso")):
        return "identity"
    if any(term in normalized for term in ("crm", "messaging", "payment", "ci")):
        return "external_service"
    return "runtime"


def _dependency_recovery_note(key: Any, label: str) -> str:
    role = _dependency_role(key)
    if role == "stateful_data":
        return f"Restore {label} from the selected snapshot and validate manifests before replay."
    if role == "observability":
        return f"Confirm {label} dashboards and alert routing after application restore."
    if role == "identity":
        return f"Confirm {label} access, emergency credentials, and callback configuration."
    if role == "external_service":
        return f"Confirm {label} availability, credentials, rate limits, and replay behavior."
    return f"Redeploy or reconfigure {label} from the last known-good release."


def _evidence_refs(spec: dict[str, Any]) -> list[dict[str, str]]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs: list[dict[str, str]] = []
    for key, prefix in (
        ("insight_ids", "insight"),
        ("signal_ids", "signal"),
        ("source_idea_ids", "idea"),
    ):
        values = evidence.get(key)
        if isinstance(values, list | tuple):
            for value in values:
                compacted = _compact(value)
                if compacted:
                    refs.append({"type": prefix, "id": compacted, "reference": f"{prefix}:{compacted}"})
    return sorted(refs, key=lambda item: (item["type"], item["id"]))


def _reference_items(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    return refs or [{"type": "none", "id": "none", "reference": "none"}]


def _acceptance_criteria(spec: dict[str, Any]) -> list[dict[str, Any]]:
    criteria = spec.get("acceptance_criteria")
    if isinstance(criteria, list):
        return [item for item in criteria if isinstance(item, dict)]
    if isinstance(criteria, dict):
        items: list[dict[str, Any]] = []
        for key in ("functional_criteria", "non_functional_criteria", "criteria"):
            value = criteria.get(key)
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        return items
    return []


def _item(
    identifier: str, name: str, description: str, derived_from: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "description": description,
        "derived_from": derived_from or [],
    }


def _dependency(
    identifier: str, name: str, role: str, recovery_note: str, derived_from: list[str]
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "role": role,
        "recovery_note": recovery_note,
        "derived_from": derived_from,
    }


def _assumption(
    identifier: str,
    name: str,
    assumption: str,
    verification: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "assumption": assumption,
        "verification": verification,
        "derived_from": derived_from,
    }


def _task(
    identifier: str,
    name: str,
    owner: str,
    action: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "owner": owner,
        "action": action,
        "derived_from": derived_from,
    }


def _communication(
    identifier: str,
    name: str,
    owner: str,
    channel: str,
    message: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "owner": owner,
        "channel": channel,
        "message": message,
        "derived_from": derived_from,
    }


def _drill(
    identifier: str,
    name: str,
    cadence: str,
    owner: str,
    exercise: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "cadence": cadence,
        "owner": owner,
        "exercise": exercise,
        "derived_from": derived_from,
    }


def _gap(
    identifier: str,
    category: str,
    description: str,
    owner: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "category": category,
        "description": description,
        "owner": owner,
        "derived_from": derived_from,
    }


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer: Any,
) -> None:
    lines.extend([f"## {title}", ""])
    if items:
        for item in items:
            lines.extend(renderer(item))
    else:
        lines.append("None.")
    lines.append("")


def _render_item(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Description: {_text(item.get('description'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_dependency(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Role: {_text(item.get('role'))}",
        f"- Recovery note: {_text(item.get('recovery_note'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_assumption(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Assumption: {_text(item.get('assumption'))}",
        f"- Verification: {_text(item.get('verification'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_task(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_communication(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Channel: {_text(item.get('channel'))}",
        f"- Message: {_text(item.get('message'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        "",
        f"- Responsibility: {_text(item.get('responsibility'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_drill(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Cadence: {_text(item.get('cadence'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Exercise: {_text(item.get('exercise'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _render_ref(item: dict[str, Any]) -> list[str]:
    reference = _text(item.get("reference"))
    if reference == "none":
        return ["- None.", ""]
    return [f"- `{reference}`", ""]


def _render_gap(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Derived from: {_derived_from(item)}",
        "",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for item in _dict_items(plan.get("recovery_objectives")):
        rows.append(
            _csv_row(
                plan,
                section="recovery_objectives",
                type_="objective",
                item_id=item.get("id"),
                name=item.get("name"),
                objective=item.get("description") or item.get("objective"),
                description=item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(plan.get("critical_systems") or plan.get("critical_dependencies")):
        rows.append(
            _csv_row(
                plan,
                section="critical_dependencies",
                type_="critical_dependency",
                field="critical_system",
                item_id=item.get("id"),
                name=item.get("name") or item.get("system"),
                category=item.get("role") or item.get("category"),
                critical_system=item.get("name") or item.get("system"),
                procedure=item.get("recovery_note") or item.get("procedure"),
                description=item.get("recovery_note") or item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(plan.get("critical_capabilities")):
        rows.append(
            _csv_row(
                plan,
                section="critical_capabilities",
                type_="critical_capability",
                field="description",
                item_id=item.get("id"),
                name=item.get("name"),
                description=item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(plan.get("failure_scenarios") or plan.get("scenarios")):
        rows.append(
            _csv_row(
                plan,
                section="failure_scenarios",
                type_="scenario",
                field="scenario",
                item_id=item.get("id"),
                name=item.get("name") or item.get("title"),
                category=item.get("category"),
                severity=item.get("severity"),
                owner=item.get("owner"),
                critical_system=item.get("critical_system") or item.get("system"),
                scenario=item.get("scenario") or item.get("description") or item.get("trigger"),
                description=item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for section, items in (
        ("backup_restore_assumptions", plan.get("backup_restore_assumptions")),
        ("backup_strategy", plan.get("backup_strategy")),
        ("backup_restore_procedures", plan.get("backup_restore_procedures")),
        ("failover_steps", plan.get("failover_steps")),
        ("restore_sequence", plan.get("restore_sequence")),
        ("data_integrity_checks", plan.get("data_integrity_checks")),
        ("validation_checks", plan.get("validation_checks")),
    ):
        for item in _dict_items(items):
            rows.append(_procedure_csv_row(plan, section, item))

    for item in _dict_items(plan.get("communications") or plan.get("communication_steps")):
        rows.append(
            _csv_row(
                plan,
                section="communications",
                type_="communication",
                field="step",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                channel=item.get("channel"),
                step=item.get("message") or item.get("action") or item.get("step"),
                description=item.get("message") or item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(plan.get("owner_roles") or plan.get("owners")):
        rows.append(
            _csv_row(
                plan,
                section="owners",
                type_="owner",
                field="description",
                item_id=item.get("id"),
                name=item.get("role") or item.get("name"),
                owner=item.get("owner") or item.get("role") or item.get("name"),
                description=item.get("responsibility") or item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(plan.get("validation_drills")):
        rows.append(
            _csv_row(
                plan,
                section="validation_drills",
                type_="validation_cadence",
                field="step",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                timing=item.get("cadence"),
                cadence=item.get("cadence"),
                step=item.get("exercise"),
                description=item.get("exercise"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(plan.get("gaps")):
        rows.append(
            _csv_row(
                plan,
                section="gaps",
                type_="gap",
                field="description",
                item_id=item.get("id"),
                name=item.get("category"),
                category=item.get("category"),
                owner=item.get("owner"),
                description=item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    return rows


def _procedure_csv_row(plan: dict[str, Any], section: str, item: dict[str, Any]) -> dict[str, str]:
    procedure = item.get("action") or item.get("assumption") or item.get("procedure")
    return _csv_row(
        plan,
        section=section,
        type_="procedure",
        field="procedure",
        item_id=item.get("id"),
        name=item.get("name"),
        owner=item.get("owner"),
        procedure=procedure,
        step=procedure or item.get("step"),
        description=item.get("description") or item.get("assumption") or item.get("action"),
        verification=item.get("verification"),
        derived_from=item.get("derived_from"),
    )


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    type_: str,
    field: Any = None,
    item_id: Any = None,
    name: Any = None,
    category: Any = None,
    severity: Any = None,
    owner: Any = None,
    timing: Any = None,
    cadence: Any = None,
    channel: Any = None,
    critical_system: Any = None,
    scenario: Any = None,
    procedure: Any = None,
    step: Any = None,
    objective: Any = None,
    description: Any = None,
    verification: Any = None,
    derived_from: Any = None,
) -> dict[str, str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "field": field or _default_csv_field(
            objective=objective,
            scenario=scenario,
            procedure=procedure,
            step=step,
            critical_system=critical_system,
            description=description,
        ),
        "source_idea_id": source.get("idea_id"),
        "title": summary.get("title"),
        "item_id": item_id,
        "name": name,
        "category": category,
        "severity": severity,
        "owner": owner,
        "timing": timing or _summary_timing(summary),
        "cadence": cadence,
        "channel": channel,
        "recovery_time_objective": summary.get("recovery_time_objective"),
        "recovery_point_objective": summary.get("recovery_point_objective"),
        "critical_system": critical_system,
        "scenario": scenario,
        "procedure": procedure,
        "step": step,
        "objective": objective,
        "description": description,
        "verification": verification,
        "derived_from": derived_from,
    }
    return {column: _csv_text(values.get(column)) for column in DISASTER_RECOVERY_PLAN_CSV_COLUMNS}


def _default_csv_field(
    *,
    objective: Any = None,
    scenario: Any = None,
    procedure: Any = None,
    step: Any = None,
    critical_system: Any = None,
    description: Any = None,
) -> str:
    if objective:
        return "objective"
    if scenario:
        return "scenario"
    if procedure:
        return "procedure"
    if step:
        return "step"
    if critical_system:
        return "critical_system"
    if description:
        return "description"
    return ""


def _summary_timing(summary: dict[str, Any]) -> str:
    rto = _compact(summary.get("recovery_time_objective"))
    rpo = _compact(summary.get("recovery_point_objective"))
    parts = []
    if rto:
        parts.append(f"RTO: {rto}")
    if rpo:
        parts.append(f"RPO: {rpo}")
    return "; ".join(parts)


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}: {_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    if isinstance(value, list | tuple | set):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    return _compact(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _derived_from(item: dict[str, Any]) -> str:
    values = item.get("derived_from")
    if not isinstance(values, list | tuple) or not values:
        return "none"
    return ", ".join(_text(value) for value in values if _text(value)) or "none"


def _haystack(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            parts.append(_compact(key))
            parts.append(_haystack(value[key]))
    elif isinstance(value, list | tuple | set):
        for item in value:
            parts.append(_haystack(item))
    else:
        parts.append(_compact(value))
    return " ".join(part for part in parts if part).lower()


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _compact(value: Any) -> str:
    return _text(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
