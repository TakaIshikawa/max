"""Generate deterministic launch freeze readiness plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.launch_freeze_readiness_plan.v1"
KIND = "max.spec.launch_freeze_readiness_plan"


def generate_launch_freeze_readiness_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    window = compact(hints.get("freeze_window") or hints.get("window")) or "launch freeze window"
    scope = _values(hints.get("freeze_scope") or hints.get("scope"), ctx["mvp_scope"] or [ctx["workflow_context"]])
    exceptions = _records(hints.get("allowed_exceptions") or hints.get("exceptions"), "exception", [{"name": "severity one fix", "owner": "release_owner", "description": "Permit only approved emergency fixes during freeze."}])
    checkpoints = _records(hints.get("dependency_checkpoints") or hints.get("checkpoints"), "checkpoint", [{"name": "dependency readiness", "owner": "release_owner", "description": "Confirm dependencies are frozen or explicitly approved."}])
    entry = _records(hints.get("entry_criteria"), "criterion", [{"name": "freeze entry approval", "owner": "release_owner", "description": "All planned changes merged, tested, and approved before freeze starts."}])
    exit_criteria = _records(hints.get("exit_criteria"), "criterion", [{"name": "launch complete", "owner": "release_owner", "description": "Release monitoring and rollback window are complete."}])
    communications = _values(hints.get("communication_channels") or hints.get("communications"), ["release channel", "stakeholder update"])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "freeze controls check", "owner": "release_owner", "description": "Validate branch, deploy, exception, and communication controls."}])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, freeze_window=window, scope_count=len(scope)),
        "freeze_window": {"window": window, "owner": compact(hints.get("owner")) or "release_owner", "evidence_reference_ids": evidence_ids},
        "freeze_scope": [_named("SCOPE", index, item, "release_owner", evidence_ids) for index, item in enumerate(scope, start=1)],
        "allowed_exceptions": [_item("EXC", index, row, evidence_ids) for index, row in enumerate(exceptions, start=1)],
        "dependency_checkpoints": [_item("DEP", index, row, evidence_ids) for index, row in enumerate(checkpoints, start=1)],
        "entry_criteria": [_item("ENT", index, row, evidence_ids) for index, row in enumerate(entry, start=1)],
        "exit_criteria": [_item("EXIT", index, row, evidence_ids) for index, row in enumerate(exit_criteria, start=1)],
        "communications": [_named("COM", index, channel, "communications_owner", evidence_ids) for index, channel in enumerate(communications, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("launch_freeze_readiness")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("exception") or item.get("checkpoint") or item.get("criterion") or item.get("check")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _named(prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": name, "owner": owner, "evidence_reference_ids": evidence_ids}


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "release_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
