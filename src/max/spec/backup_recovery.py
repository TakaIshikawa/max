"""Generate deterministic backup and recovery plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


BACKUP_RECOVERY_SCHEMA_VERSION = "max-backup-recovery/v1"

BACKUP_RECOVERY_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "source_idea_id",
    "plan_id",
    "plan_type",
    "plan_category",
    "plan_title",
    "plan_owner",
    "plan_priority",
    "backup_frequency",
    "retention_period",
    "recovery_time_objective",
    "recovery_point_objective",
    "backup_scope",
    "backup_mechanism",
    "verification_procedure",
    "restoration_procedure",
    "source_fields",
)

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_backup_recovery_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic backup and recovery guidance."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source")
    source = source if isinstance(source, dict) else {}
    project = spec.get("project")
    project = project if isinstance(project, dict) else {}
    solution = spec.get("solution")
    solution = solution if isinstance(solution, dict) else {}
    execution = spec.get("execution")
    execution = execution if isinstance(execution, dict) else {}

    context = _backup_context(spec, project, solution, execution)
    plans = _backup_plan_records(context)
    plans = _prioritize_plans(plans)

    return {
        "schema_version": BACKUP_RECOVERY_SCHEMA_VERSION,
        "kind": "max.backup_recovery_plan",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": _compact(project.get("title"))
            or _compact(source.get("idea_id"))
            or "Untitled TactSpec",
            "plan_count": len(plans),
            "critical_plan_count": sum(1 for item in plans if item["priority"] == "critical"),
            "high_plan_count": sum(1 for item in plans if item["priority"] == "high"),
        },
        "backup_plans": plans,
    }


def render_backup_recovery_plan_csv(plan: dict[str, Any]) -> str:
    """Render backup and recovery plans as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(BACKUP_RECOVERY_CSV_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(plan or {}):
        writer.writerow(row)  # type: ignore[arg-type]
    return output.getvalue()


def _backup_context(
    spec: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    stack = solution.get("suggested_stack")
    text = _haystack(spec)

    has_database = _contains_any(
        text, ("database", "postgres", "mysql", "mongodb", "sql", "datastore", "db")
    )
    has_user_data = _contains_any(
        text, ("customer", "user data", "pii", "personal data", "account", "email")
    )
    has_files = _contains_any(text, ("file", "storage", "s3", "blob", "document", "upload"))
    has_state = _contains_any(text, ("state", "session", "cache", "redis", "memcached"))
    has_config = _contains_any(text, ("config", "setting", "environment", "secret", "credential"))

    return {
        "workflow_context": _workflow(project),
        "stack_components": _stack_components(stack),
        "has_database": has_database,
        "has_user_data": has_user_data,
        "has_files": has_files,
        "has_state": has_state,
        "has_config": has_config,
        "execution_risks": [
            _compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)
        ],
    }


def _backup_plan_records(context: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = context["workflow_context"]
    records: list[dict[str, Any]] = []

    # Database backup plan
    if context["has_database"]:
        records.append(
            _plan(
                plan_type="database",
                plan_category="data_backup",
                plan_title="Database backup",
                plan_owner="data_owner",
                plan_priority="critical" if context["has_user_data"] else "high",
                backup_frequency="Daily",
                retention_period="30 days",
                recovery_time_objective="1 hour",
                recovery_point_objective="24 hours",
                backup_scope="Full database backup with transaction logs",
                backup_mechanism="Automated database snapshot with incremental transaction log backups",
                verification_procedure="Run automated restore test weekly; verify data integrity checksums",
                restoration_procedure="Restore from latest snapshot; apply transaction logs; verify schema and data consistency",
                source_fields=["solution.suggested_stack", "data_model"],
            )
        )
    else:
        records.append(
            _plan(
                plan_type="database",
                plan_category="data_backup",
                plan_title="Database backup strategy",
                plan_owner="data_owner",
                plan_priority="medium",
                backup_frequency="Not applicable",
                retention_period="N/A",
                recovery_time_objective="N/A",
                recovery_point_objective="N/A",
                backup_scope="Determine if persistent data storage is required",
                backup_mechanism="If database is added, implement automated backup strategy",
                verification_procedure="Document backup requirements when data persistence is needed",
                restoration_procedure="Plan restoration procedure if database is introduced",
                source_fields=["solution.suggested_stack"],
            )
        )

    # File storage backup plan
    if context["has_files"]:
        records.append(
            _plan(
                plan_type="file_storage",
                plan_category="data_backup",
                plan_title="File storage backup",
                plan_owner="platform_owner",
                plan_priority="high",
                backup_frequency="Daily",
                retention_period="90 days",
                recovery_time_objective="2 hours",
                recovery_point_objective="24 hours",
                backup_scope="All user-uploaded files and generated documents",
                backup_mechanism="Cross-region replication with versioning enabled",
                verification_procedure="Monthly restore test to staging environment; verify file integrity",
                restoration_procedure="Restore from replicated storage; verify file metadata and access permissions",
                source_fields=["solution.suggested_stack", "solution.technical_approach"],
            )
        )

    # Configuration backup plan
    if context["has_config"]:
        records.append(
            _plan(
                plan_type="configuration",
                plan_category="config_backup",
                plan_title="Configuration backup",
                plan_owner="platform_owner",
                plan_priority="high",
                backup_frequency="On change",
                retention_period="Indefinite",
                recovery_time_objective="30 minutes",
                recovery_point_objective="0 (immediate)",
                backup_scope="Application configuration, secrets, and environment variables",
                backup_mechanism="Version-controlled infrastructure-as-code and encrypted secret store",
                verification_procedure="Validate deployment from configuration repository in staging",
                restoration_procedure="Deploy from version control; restore secrets from encrypted backup; verify service health",
                source_fields=["solution.suggested_stack", "execution.mvp_scope"],
            )
        )

    # Application state backup plan
    if context["has_state"]:
        records.append(
            _plan(
                plan_type="application_state",
                plan_category="state_backup",
                plan_title="Application state backup",
                plan_owner="backend_owner",
                plan_priority="medium",
                backup_frequency="Hourly",
                retention_period="7 days",
                recovery_time_objective="15 minutes",
                recovery_point_objective="1 hour",
                backup_scope="Session data, cache state, and temporary workflow data",
                backup_mechanism="Redis persistence with RDB snapshots and AOF logs",
                verification_procedure="Test cache rebuilding from backup; verify session recovery",
                restoration_procedure="Restore Redis snapshot; replay AOF if needed; verify cache warmup",
                source_fields=["solution.suggested_stack"],
            )
        )

    # Audit log backup plan
    records.append(
        _plan(
            plan_type="audit_logs",
            plan_category="log_backup",
            plan_title="Audit log backup",
            plan_owner="security_owner",
            plan_priority="high",
            backup_frequency="Continuous",
            retention_period="365 days",
            recovery_time_objective="4 hours",
            recovery_point_objective="1 hour",
            backup_scope="All security events, authentication logs, and audit trails",
            backup_mechanism="Log aggregation with archival to immutable storage",
            verification_procedure="Quarterly audit log retrieval and integrity verification",
            restoration_procedure="Query archived logs; verify completeness and chronological order",
            source_fields=["execution.validation_plan", "security"],
        )
    )

    # Code and deployment backup plan
    records.append(
        _plan(
            plan_type="code_deployment",
            plan_category="deployment_backup",
            plan_title="Code and deployment backup",
            plan_owner="engineering_owner",
            plan_priority="critical",
            backup_frequency="On deployment",
            retention_period="Indefinite",
            recovery_time_objective="30 minutes",
            recovery_point_objective="0 (immediate)",
            backup_scope="Source code, build artifacts, deployment configurations",
            backup_mechanism="Version control system with tagged releases and artifact registry",
            verification_procedure="Deploy previous release to staging; verify rollback procedure",
            restoration_procedure="Checkout tagged release; deploy from artifact registry; verify service endpoints",
            source_fields=["solution.suggested_stack", "execution.mvp_scope"],
        )
    )

    # Disaster recovery coordination plan
    records.append(
        _plan(
            plan_type="disaster_recovery",
            plan_category="recovery_coordination",
            plan_title="Disaster recovery coordination",
            plan_owner="product_owner",
            plan_priority="critical",
            backup_frequency="N/A",
            retention_period="N/A",
            recovery_time_objective=f"Aligned with {workflow} requirements",
            recovery_point_objective=f"Based on {workflow} data sensitivity",
            backup_scope="Cross-system recovery orchestration and business continuity",
            backup_mechanism="Documented runbook with recovery team roles and communication protocols",
            verification_procedure="Quarterly disaster recovery drill with full team participation",
            restoration_procedure="Follow incident response playbook; coordinate across backup plans; verify end-to-end workflow",
            source_fields=["project.workflow_context", "execution.risks"],
        )
    )

    return records


def _plan(
    *,
    plan_type: str,
    plan_category: str,
    plan_title: str,
    plan_owner: str,
    plan_priority: str,
    backup_frequency: str,
    retention_period: str,
    recovery_time_objective: str,
    recovery_point_objective: str,
    backup_scope: str,
    backup_mechanism: str,
    verification_procedure: str,
    restoration_procedure: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": "",
        "type": plan_type,
        "category": plan_category,
        "title": _compact(plan_title),
        "owner": plan_owner,
        "priority": plan_priority,
        "backup_frequency": _compact(backup_frequency),
        "retention_period": _compact(retention_period),
        "recovery_time_objective": _compact(recovery_time_objective),
        "recovery_point_objective": _compact(recovery_point_objective),
        "backup_scope": _compact(backup_scope),
        "backup_mechanism": _compact(backup_mechanism),
        "verification_procedure": _compact(verification_procedure),
        "restoration_procedure": _compact(restoration_procedure),
        "source_fields": [field for field in source_fields if field],
    }


def _prioritize_plans(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        plans,
        key=lambda item: (
            _PRIORITY_RANK.get(item["priority"], 4),
            item["type"],
        ),
    )
    return [{**item, "id": f"BP{index:02d}"} for index, item in enumerate(ordered, start=1)]


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _haystack(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            parts.append(_haystack(value[key]))
    elif isinstance(value, list):
        for item in value:
            parts.append(_haystack(item))
    elif value is not None:
        parts.append(str(value))
    return " ".join(parts).lower()


def _workflow(project: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _stack_components(stack: Any) -> list[str]:
    if not isinstance(stack, dict):
        return []
    return [_compact(value) for key, value in sorted(stack.items()) if key and _compact(value)]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    plans = plan.get("backup_plans")
    if not isinstance(plans, list):
        return []
    return [_csv_row(plan, item) for item in plans if isinstance(item, dict)]


def _csv_row(plan: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    source = plan.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "schema_version": _csv_cell(plan.get("schema_version")),
        "kind": _csv_cell(plan.get("kind")),
        "source_idea_id": _csv_cell(source.get("idea_id")),
        "plan_id": _csv_cell(item.get("id")),
        "plan_type": _csv_cell(item.get("type")),
        "plan_category": _csv_cell(item.get("category")),
        "plan_title": _csv_cell(item.get("title")),
        "plan_owner": _csv_cell(item.get("owner")),
        "plan_priority": _csv_cell(item.get("priority")),
        "backup_frequency": _csv_cell(item.get("backup_frequency")),
        "retention_period": _csv_cell(item.get("retention_period")),
        "recovery_time_objective": _csv_cell(item.get("recovery_time_objective")),
        "recovery_point_objective": _csv_cell(item.get("recovery_point_objective")),
        "backup_scope": _csv_cell(item.get("backup_scope")),
        "backup_mechanism": _csv_cell(item.get("backup_mechanism")),
        "verification_procedure": _csv_cell(item.get("verification_procedure")),
        "restoration_procedure": _csv_cell(item.get("restoration_procedure")),
        "source_fields": _csv_cell(item.get("source_fields")),
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_cell(key)}={_csv_cell(item)}"
            for key, item in sorted(value.items())
            if _csv_cell(item)
        )
    if isinstance(value, (list, tuple, set)):
        return " | ".join(_csv_cell(item) for item in _list(value) if _csv_cell(item))
    return _compact(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
