"""Generate deterministic integration contract review plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.integration_contract_review_plan.v1"
KIND = "max.spec.integration_contract_review_plan"


def generate_integration_contract_review_plan(spec_like: Any) -> dict[str, Any]:
    """Return contract checks grouped by integration or dependency."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "integration_contract_review")
    integrations = _records(hints.get("integrations") or spec.get("integrations"), "integration")
    dependencies = _records(hints.get("dependencies") or spec.get("dependencies"), "dependency")
    if not integrations and not dependencies:
        integrations = [{"name": "primary integration", "type": "integration"}]
    owners = _owner_map(hints.get("owners") or spec.get("owners"))
    evidence_ids = _evidence_ids(ctx)
    contract_checks = [_contract_group(record, owners, evidence_ids) for record in integrations + dependencies]
    follow_up_actions = _follow_ups(contract_checks)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            integration_count=len(integrations),
            dependency_count=len(dependencies),
            missing_owner_count=sum(1 for group in contract_checks if group["owner"] == "integration_owner"),
        ),
        "contract_checks": contract_checks,
        "security_privacy_checks": _security_privacy_checks(contract_checks, evidence_ids),
        "signoff_actions": _signoff_actions(contract_checks, evidence_ids),
        "follow_up_actions": follow_up_actions,
        "evidence_references": ctx["evidence_references"],
    }


def _contract_group(record: dict[str, str], owners: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    name = record["name"]
    owner = record.get("owner") or owners.get(name.casefold()) or owners.get("default") or "integration_owner"
    priority = record.get("priority") or ("high" if record["type"] == "dependency" else "medium")
    checks = [
        _check("contract_surface", owner, priority, f"Review request, response, auth, and versioned fields for {name}.", evidence_ids),
        _check("compatibility", owner, priority, f"Confirm backward compatibility, deprecation handling, and schema evolution for {name}.", evidence_ids),
        _check("failure_handling", owner, "high", f"Validate timeout, retry, idempotency, and fallback behavior for {name}.", evidence_ids),
    ]
    return {
        "name": name,
        "type": record["type"],
        "owner": owner,
        "priority": priority,
        "acceptance_signal": record.get("acceptance_signal") or f"{name} contract reviewed and signed off",
        "evidence_reference_ids": evidence_ids,
        "checks": checks,
    }


def _security_privacy_checks(groups: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _check(
            "security_privacy",
            group["owner"],
            "high",
            f"Confirm auth scope, secrets handling, data classification, processor posture, and audit logging for {group['name']}.",
            evidence_ids,
            target=group["name"],
        )
        for group in groups
    ]


def _signoff_actions(groups: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _check(
            "signoff",
            group["owner"],
            group["priority"],
            f"Record contract review signoff for {group['name']} with owner, date, decision, and residual exceptions.",
            evidence_ids,
            target=group["name"],
        )
        for group in groups
    ]


def _follow_ups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        if group["owner"] == "integration_owner":
            actions.append(
                {
                    "id": f"FU{index}",
                    "type": "missing_owner",
                    "target": group["name"],
                    "owner": "release_manager",
                    "priority": "high",
                    "action": f"Assign a named owner for {group['name']} before contract review signoff.",
                    "acceptance_signal": "Named owner is recorded in the review plan.",
                    "evidence_reference_ids": group["evidence_reference_ids"],
                }
            )
    return actions


def _records(value: Any, default_type: str) -> list[dict[str, str]]:
    values = value if isinstance(value, list) else string_list(value)
    records: list[dict[str, str]] = []
    for index, item in enumerate(values, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("id") or item.get("service") or item.get("api")) or f"{default_type} {index}"
            records.append(
                {
                    "name": name,
                    "type": compact(item.get("type")) or default_type,
                    "owner": compact(item.get("owner")),
                    "priority": _priority(item.get("priority") or item.get("severity")),
                    "acceptance_signal": compact(item.get("acceptance_signal")),
                }
            )
        else:
            name = compact(item) or f"{default_type} {index}"
            records.append({"name": name, "type": default_type, "owner": "", "priority": "", "acceptance_signal": ""})
    return sorted(records, key=lambda item: (item["type"].casefold(), item["name"].casefold()))


def _check(
    check_type: str,
    owner: str,
    priority: str,
    description: str,
    evidence_ids: list[str],
    *,
    target: str | None = None,
) -> dict[str, Any]:
    return {
        "type": check_type,
        "target": target,
        "owner": owner,
        "priority": priority,
        "acceptance_signal": f"{check_type.replace('_', ' ')} accepted",
        "description": description,
        "evidence_reference_ids": evidence_ids,
    }


def _owner_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {compact(key).casefold(): compact(owner) for key, owner in value.items() if compact(key) and compact(owner)}


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _priority(value: Any) -> str:
    text = compact(value).casefold()
    return text if text in {"critical", "high", "medium", "low"} else ""


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
