"""Generate deterministic API version deprecation plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.api_version_deprecation_plan.v1"
API_VERSION_DEPRECATION_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.api_version_deprecation_plan"


def generate_api_version_deprecation_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic planning data for API version deprecation."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _api_version_hints(spec, ctx)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    strictness = "strict" if hints["breaking"] or hints["public_api"] or hints["external_consumers"] else ctx["strictness"]
    migration_window = _migration_window(hints, strictness)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            deprecation_strictness=strictness,
            deprecated_version=hints["deprecated_version"],
            replacement_version=hints["replacement_version"],
            migration_window_days=migration_window,
            public_api=hints["public_api"],
        ),
        "deprecation_policy": _deprecation_policy(hints, strictness, migration_window, evidence_ids),
        "affected_consumers": _affected_consumers(hints, strictness, evidence_ids),
        "migration_timeline": _migration_timeline(hints, strictness, migration_window, evidence_ids),
        "compatibility_checks": _compatibility_checks(hints, strictness, evidence_ids),
        "communication_schedule": _communication_schedule(hints, strictness, migration_window, evidence_ids),
        "rollback_or_extension_criteria": _rollback_or_extension_criteria(hints, strictness, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _api_version_hints(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    api = metadata.get("api_deprecation") if isinstance(metadata.get("api_deprecation"), dict) else {}
    api_versions = metadata.get("api_versions") if isinstance(metadata.get("api_versions"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}

    deprecated_version = compact(api.get("deprecated_version") or api_versions.get("deprecated") or api_versions.get("current")) or "v1"
    replacement_version = compact(api.get("replacement_version") or api_versions.get("replacement") or api_versions.get("target")) or "v2"
    consumers = _ordered(
        string_list(api.get("consumers"))
        + string_list(api.get("affected_consumers"))
        + string_list(api_versions.get("consumers"))
        + string_list(project.get("target_users"))
    ) or ["default API consumer"]
    surfaces = _ordered(
        string_list(api.get("surfaces"))
        + string_list(api_versions.get("surfaces"))
        + string_list(execution.get("mvp_scope"))
    ) or ["primary API surface"]
    text = " ".join(
        [deprecated_version, replacement_version]
        + consumers
        + surfaces
        + string_list(execution.get("risks"))
        + [
            compact(api.get("impact")),
            compact(api.get("visibility")),
            compact(api.get("change_type")),
            compact(project.get("workflow_context")),
            compact(project.get("summary")),
        ]
    ).lower()
    explicit_consumers = bool(
        string_list(api.get("consumers")) + string_list(api.get("affected_consumers")) + string_list(api_versions.get("consumers"))
    )

    return {
        "deprecated_version": deprecated_version,
        "replacement_version": replacement_version,
        "consumers": consumers,
        "surfaces": surfaces,
        "notice_days": _number(api.get("notice_days") or api_versions.get("notice_days")),
        "breaking": _truthy(api.get("breaking")) or any(term in text for term in ("breaking", "remove", "incompatible", "contract change")),
        "public_api": _truthy(api.get("public_api")) or any(term in text for term in ("public api", "external api", "partner api", "customer api")),
        "external_consumers": explicit_consumers or any(term in text for term in ("partner", "customer", "mobile", "external", "developer")),
        "removal_date": compact(api.get("removal_date") or api_versions.get("removal_date")) or "planned removal date",
    }


def _migration_window(hints: dict[str, Any], strictness: str) -> int:
    if hints["notice_days"]:
        return max(hints["notice_days"], 90 if strictness == "strict" else 30)
    return 180 if strictness == "strict" else 60


def _deprecation_policy(
    hints: dict[str, Any], strictness: str, migration_window: int, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "DP1",
        "name": "API version deprecation policy",
        "owner": "api_owner",
        "strictness": strictness,
        "deprecated_version": hints["deprecated_version"],
        "replacement_version": hints["replacement_version"],
        "migration_window_days": migration_window,
        "removal_gate": "all critical consumers migrated and compatibility checks pass" if strictness == "strict" else "migration guidance published and usage reviewed",
        "evidence_reference_ids": evidence_ids,
    }


def _affected_consumers(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"AC{index}",
            "consumer": consumer,
            "owner": "customer_success_owner" if strictness == "strict" else "api_owner",
            "deprecated_version": hints["deprecated_version"],
            "replacement_version": hints["replacement_version"],
            "migration_status": "contact and migration plan required" if strictness == "strict" else "migration owner to confirm",
            "evidence_reference_ids": evidence_ids,
        }
        for index, consumer in enumerate(hints["consumers"], start=1)
    ]


def _migration_timeline(
    hints: dict[str, Any], strictness: str, migration_window: int, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    milestones = [
        ("MT1", "day 0", "Publish deprecation policy, replacement docs, and migration examples."),
        ("MT2", f"day {max(migration_window - 30, 1)}", "Confirm migration readiness and unresolved consumer blockers."),
        ("MT3", f"day {migration_window}", f"Remove or disable {hints['deprecated_version']} only after gates pass."),
    ]
    if strictness == "strict":
        milestones.insert(1, ("MT2", "day 30", "Hold office hours and review top consumer migration plans."))
        milestones[2] = ("MT3", f"day {max(migration_window - 60, 30)}", "Escalate unmigrated critical consumers and extension requests.")
        milestones[3] = ("MT4", f"day {migration_window}", f"Remove or disable {hints['deprecated_version']} only after executive approval.")
    return [
        {
            "id": item_id,
            "milestone": milestone,
            "owner": "api_owner" if item_id in {"MT1", "MT4"} else "customer_success_owner",
            "action": action,
            "strictness": strictness,
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, milestone, action in milestones
    ]


def _compatibility_checks(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    checks = [
        ("CC1", "Contract parity", "Confirm replacement endpoints cover required request and response contracts."),
        ("CC2", "Telemetry readiness", "Confirm usage metrics identify consumers still calling the deprecated version."),
        ("CC3", "Client migration test", "Confirm example clients and SDKs work against the replacement version."),
    ]
    if strictness == "strict":
        checks.extend(
            [
                ("CC4", "Breaking-change waiver review", "Confirm critical breaking changes have approved mitigations."),
                ("CC5", "Removal dry run", "Confirm disabling deprecated traffic fails safely and can be restored."),
            ]
        )
    return [
        {
            "id": item_id,
            "name": name,
            "owner": "api_owner",
            "required": True,
            "strictness": strictness,
            "description": description,
            "surfaces": hints["surfaces"],
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, name, description in checks
    ]


def _communication_schedule(
    hints: dict[str, Any], strictness: str, migration_window: int, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    reminders = [migration_window, 30, 14, 7] if strictness == "strict" else [migration_window, 14]
    return [
        {
            "id": f"CS{index}",
            "timing": f"{days} days before removal" if days != migration_window else "deprecation announcement",
            "owner": "developer_relations_owner" if strictness == "strict" else "api_owner",
            "message": f"Notify consumers to migrate from {hints['deprecated_version']} to {hints['replacement_version']}.",
            "channels": ["email", "developer portal", "status page", "account team"] if strictness == "strict" else ["email", "developer portal"],
            "evidence_reference_ids": evidence_ids,
        }
        for index, days in enumerate(reminders, start=1)
    ]


def _rollback_or_extension_criteria(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "RE1",
            "name": "Extension approval",
            "owner": "api_owner",
            "condition": "critical consumer blocker, unmigrated high-volume traffic, or replacement instability",
            "action": "extend migration window and publish revised removal date" if strictness == "strict" else "document extension decision",
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "RE2",
            "name": "Rollback trigger",
            "owner": "on_call_owner",
            "condition": "post-removal error budget breach, authentication failure spike, or unexpected customer impact",
            "action": f"restore {hints['deprecated_version']} compatibility while remediation is completed",
            "evidence_reference_ids": evidence_ids,
        },
    ]


def _ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)


def _number(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"1", "true", "yes", "y", "required", "public", "breaking"}
