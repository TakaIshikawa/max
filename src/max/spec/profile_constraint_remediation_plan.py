"""Generate deterministic profile constraint remediation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, summary

SCHEMA_VERSION = "max.spec.profile_constraint_remediation_plan.v1"
KIND = "max.spec.profile_constraint_remediation_plan"


def generate_profile_constraint_remediation_plan(profile: Any, violations: Any, *, target_date: str | None = None) -> dict[str, Any]:
    ctx = context({})
    profile_row = _profile(profile)
    violation_rows = _violations(violations, profile_row)
    tasks = _tasks(violation_rows, target_date)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, profile_id=profile_row["profile_id"], violation_count=len(violation_rows), blocking_count=sum(1 for item in violation_rows if item["type"] == "blocking"), target_date=target_date),
        "profile": profile_row,
        "severity_triage": violation_rows,
        "remediation_tasks": tasks,
        "validation_checks": _validation_checks(tasks),
        "rollout_gates": _rollout_gates(),
        "evidence_references": ctx["evidence_references"],
    }


def _profile(value: Any) -> dict[str, str]:
    item = value if isinstance(value, dict) else {}
    return {
        "profile_id": compact(item.get("profile_id") or item.get("id")) or "missing_profile",
        "name": compact(item.get("name")) or compact(item.get("profile_id") or item.get("id")) or "Missing profile",
        "owner": compact(item.get("owner")) or "profile_owner",
        "status": "provided" if isinstance(value, dict) and value else "missing",
    }


def _violations(value: Any, profile: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        severity = compact(item.get("severity")) or "advisory"
        violation_type = "blocking" if severity.casefold() in {"blocker", "blocking", "critical", "high"} or item.get("blocking") is True else "advisory"
        rows.append(
            {
                "id": compact(item.get("violation_id") or item.get("id")) or f"violation_{index}",
                "profile_id": compact(item.get("profile_id")) or profile["profile_id"],
                "constraint": compact(item.get("constraint")) or compact(item.get("name")) or f"constraint_{index}",
                "severity": severity,
                "type": violation_type,
                "owner": compact(item.get("owner")) or profile["owner"],
            }
        )
    return sorted(rows, key=lambda row: (0 if row["type"] == "blocking" else 1, row["constraint"].casefold(), row["id"].casefold()))


def _tasks(violations: list[dict[str, str]], target_date: str | None) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for violation in violations:
        task = {
            "id": f"PCR{len(tasks) + 1}",
            "violation_id": violation["id"],
            "constraint": violation["constraint"],
            "type": violation["type"],
            "owner": violation["owner"],
            "action": "Block rollout and remediate constraint before release." if violation["type"] == "blocking" else "Schedule advisory remediation and document accepted risk.",
        }
        if target_date:
            task["target_date"] = target_date
        tasks.append(task)
    return tasks


def _validation_checks(tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"PCV{index}", "constraint": task["constraint"], "task_id": task["id"], "check": "Verify constraint passes automated and owner-reviewed validation."} for index, task in enumerate(tasks, start=1)]


def _rollout_gates() -> list[dict[str, str]]:
    return [
        {"id": "PCG1", "name": "blocking_clearance", "description": "No blocking constraint violations remain before rollout."},
        {"id": "PCG2", "name": "owner_approval", "description": "Profile owner approves remediation evidence and advisory exceptions."},
    ]
