"""Generate deterministic rollback validation evidence plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.rollback_validation_evidence_plan.v1"
KIND = "max.spec.rollback_validation_evidence_plan"


def generate_rollback_validation_evidence_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    evidence_ids = _evidence_ids(ctx)
    scenarios = _records(hints.get("rollback_scenarios") or hints.get("scenarios"), "scenario", [{"name": f"{ctx['workflow_context']} rollback", "owner": "release_owner", "description": "Rollback primary workflow change and confirm stable state."}])
    artifacts = _records(hints.get("evidence_artifacts") or hints.get("artifacts"), "artifact", [{"name": "rollback execution log", "owner": "release_owner", "description": "Capture rollback command output, timestamps, and operator notes."}])
    checks = _records(hints.get("validation_checks"), "check", [{"name": "post-rollback smoke check", "owner": "qa_owner", "description": "Confirm critical workflow succeeds after rollback."}])
    reconciliation = _records(hints.get("reconciliation_steps") or hints.get("reconciliation"), "step", [{"name": "state reconciliation", "owner": "engineering_owner", "description": "Reconcile data, jobs, and customer-visible state after rollback."}])
    signoffs = _records(hints.get("signoffs") or hints.get("owners"), "signoff", [{"name": "release acceptance", "owner": compact(hints.get("release_owner")) or "release_owner", "description": "Approve rollback evidence package."}])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, scenario_count=len(scenarios), artifact_count=len(artifacts)),
        "rollback_scenarios": [_item("RS", index, row, evidence_ids) for index, row in enumerate(scenarios, start=1)],
        "evidence_artifacts": [_item("EA", index, row, evidence_ids) for index, row in enumerate(artifacts, start=1)],
        "validation_checks": [_item("VC", index, row, evidence_ids) for index, row in enumerate(checks, start=1)],
        "reconciliation_steps": [_item("REC", index, row, evidence_ids) for index, row in enumerate(reconciliation, start=1)],
        "signoffs": [_item("SO", index, row, evidence_ids) for index, row in enumerate(signoffs, start=1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("rollback_validation_evidence")
    return hints if isinstance(hints, dict) else {}


def _records(value: Any, default_name: str, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("scenario") or item.get("artifact") or item.get("check") or item.get("criterion")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("description") or item.get("pass_fail_criteria") or item.get("criteria"))})
        else:
            rows.append({"name": compact(item) or f"{default_name} {index}", "owner": "", "description": ""})
    return sorted(rows or fallback, key=lambda row: row["name"].casefold())


def _item(prefix: str, index: int, row: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"{prefix}{index}", "name": row["name"], "owner": row["owner"] or "release_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
