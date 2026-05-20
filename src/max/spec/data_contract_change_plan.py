"""Generate deterministic data contract change plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_contract_change_plan.v1"
KIND = "max.spec.data_contract_change_plan"


def generate_data_contract_change_plan(spec_like: Any) -> dict[str, Any]:
    """Return producer, consumer, migration, and rollout controls for contract changes."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    producers = _parties(hints.get("producers") or hints.get("producer") or spec.get("producers"), "producer", ["source service"])
    consumers = _parties(hints.get("consumers") or hints.get("consumer") or spec.get("consumers"), "consumer", [ctx["target_user"]])
    severity = _severity(hints.get("breaking_change") or hints.get("severity") or hints.get("compatibility"))
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            change_name=compact(hints.get("name") or hints.get("contract") or spec.get("contract_name")) or ctx["title"],
            breaking_change_severity=severity,
            producer_count=len(producers),
            consumer_count=len(consumers),
        ),
        "impacted_parties": _impacted_parties(producers, consumers, evidence_ids),
        "compatibility_checks": _compatibility_checks(hints, severity, evidence_ids),
        "migration_steps": _steps(hints.get("migration_steps"), _default_migration_steps(severity), "MS", evidence_ids),
        "rollout_gates": _steps(hints.get("rollout_gates") or hints.get("gates"), _default_rollout_gates(severity), "RG", evidence_ids),
        "rollback_criteria": _steps(
            hints.get("rollback_criteria") or hints.get("rollback"),
            _default_rollback_criteria(severity),
            "RC",
            evidence_ids,
        ),
        "owner_roles": _owner_roles(hints, producers, consumers),
        "evidence_references": ctx["evidence_references"],
    }


def _impacted_parties(producers: list[dict[str, str]], consumers: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    parties = producers + consumers
    return [
        {
            "id": f"IP{index}",
            "role": item["role"],
            "name": item["name"],
            "owner": item["owner"],
            "impact": item["impact"] or f"Validate {item['role']} compatibility with the contract change.",
            "evidence_reference_ids": evidence_ids,
        }
        for index, item in enumerate(sorted(parties, key=lambda row: (row["role"], row["name"].casefold())), start=1)
    ]


def _compatibility_checks(hints: dict[str, Any], severity: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    raw = hints.get("compatibility_checks") or hints.get("checks")
    checks = _records(raw, "check")
    if not checks:
        checks = [
            {"name": "schema diff review", "owner": "data_contract_owner", "description": "Compare old and new schema fields, types, nullability, and defaults."},
            {"name": "consumer contract test", "owner": "qa_owner", "description": "Run consumer contract tests against the changed payload."},
            {"name": "versioning policy", "owner": "platform_owner", "description": "Confirm version, deprecation, and compatibility policy is documented."},
        ]
    if severity in {"breaking", "high"}:
        checks.append(
            {
                "name": "breaking change approval",
                "owner": "architecture_owner",
                "description": "Record explicit approval for incompatible field or semantic changes.",
            }
        )
    return [
        {
            "id": f"CC{index}",
            "name": check["name"],
            "owner": check["owner"] or "data_contract_owner",
            "severity": severity,
            "description": check["description"] or f"Confirm {check['name']} before rollout.",
            "evidence_reference_ids": evidence_ids,
        }
        for index, check in enumerate(sorted(checks, key=lambda row: row["name"].casefold()), start=1)
    ]


def _steps(value: Any, fallback: list[str], prefix: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    records = _records(value, "step") or [{"name": item, "owner": "", "description": item} for item in fallback]
    return [
        {
            "id": f"{prefix}{index}",
            "name": record["name"],
            "owner": record["owner"] or ("release_manager" if prefix == "RG" else "data_contract_owner"),
            "description": record["description"] or record["name"],
            "evidence_reference_ids": evidence_ids,
        }
        for index, record in enumerate(sorted(records, key=lambda row: row["name"].casefold()), start=1)
    ]


def _owner_roles(hints: dict[str, Any], producers: list[dict[str, str]], consumers: list[dict[str, str]]) -> list[dict[str, str]]:
    owners = _owner_map(hints.get("owners"))
    roles = [
        ("data_contract_owner", owners.get("data_contract_owner") or producers[0]["owner"], "Own schema diff, compatibility decision, and signed contract baseline."),
        ("consumer_owner", owners.get("consumer_owner") or consumers[0]["owner"], "Confirm consumer readiness and adoption window."),
        ("release_manager", owners.get("release_manager") or "release_manager", "Coordinate rollout gates, migration sequencing, and rollback decision."),
    ]
    return [{"role": role, "owner": owner, "responsibility": responsibility} for role, owner, responsibility in roles]


def _parties(value: Any, role: str, fallback: list[str]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("service") or item.get("team")) or f"{role} {index}"
            owner = compact(item.get("owner")) or f"{role}_owner"
            impact = compact(item.get("impact") or item.get("change"))
        else:
            name = compact(item) or f"{role} {index}"
            owner = f"{role}_owner"
            impact = ""
        rows.append({"role": role, "name": name, "owner": owner, "impact": impact})
    if not rows:
        rows = [{"role": role, "name": item, "owner": f"{role}_owner", "impact": ""} for item in fallback]
    return sorted(rows, key=lambda row: row["name"].casefold())


def _records(value: Any, default_name: str) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("title") or item.get("gate") or item.get("criterion")) or f"{default_name} {index}"
            rows.append({"name": name, "owner": compact(item.get("owner")), "description": compact(item.get("description") or item.get("action") or item.get("check"))})
        else:
            name = compact(item) or f"{default_name} {index}"
            rows.append({"name": name, "owner": "", "description": name})
    return rows


def _default_migration_steps(severity: str) -> list[str]:
    steps = ["publish versioned contract", "update producer payload", "validate consumer contract tests"]
    if severity in {"breaking", "high"}:
        steps.insert(0, "announce breaking-change migration window")
    return steps


def _default_rollout_gates(severity: str) -> list[str]:
    gates = ["contract tests pass", "consumer owners acknowledge readiness", "monitoring dashboard reviewed"]
    if severity in {"breaking", "high"}:
        gates.append("breaking-change approval recorded")
    return gates


def _default_rollback_criteria(severity: str) -> list[str]:
    criteria = ["consumer error rate exceeds agreed threshold", "schema validation failures appear in production"]
    if severity in {"breaking", "high"}:
        criteria.append("critical consumer cannot complete migration")
    return criteria


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("data_contract_change")
    return hints if isinstance(hints, dict) else {}


def _severity(value: Any) -> str:
    if isinstance(value, bool):
        return "breaking" if value else "compatible"
    text = compact(value).casefold()
    if text in {"breaking", "high", "major", "incompatible", "true", "yes"}:
        return "breaking"
    if text in {"compatible", "low", "minor", "additive", "false", "no"}:
        return "compatible"
    return "standard"


def _owner_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {compact(key): compact(owner) for key, owner in value.items() if compact(key) and compact(owner)}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
