"""Generate deterministic spec generation recovery plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.spec_generation_recovery_plan.v1"
KIND = "max.spec.spec_generation_recovery_plan"


def generate_spec_generation_recovery_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "spec_generation_recovery")
    failures = _failures(hints)
    groups = _groups(failures, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Spec Generation Recovery Plan",
        "summary": source_summary(ctx, failure_count=len(failures), failure_group_count=len(groups)),
        "failure_groups": groups,
        "retry_order": _retry_order(groups, evidence_ids),
        "repair_actions": _repair_actions(groups, evidence_ids),
        "budget_checks": _budget_checks(groups, evidence_ids),
        "validation_steps": section(hints, ("validation_steps", "validation", "checks"), "SGV", "spec_owner", "Validate recovered spec generation", evidence_ids, ["rerun generation, verify rendered spec sections, and compare evidence references before publication"]),
        "rollback_steps": section(hints, ("rollback_steps", "rollback"), "SGB", "release_owner", "Rollback failed spec generation", evidence_ids, ["pause publication queue, restore last approved spec artifact, and notify downstream reviewers"]),
        "evidence_references": ctx["evidence_references"],
    }


def _failures(hints: dict[str, Any]) -> list[dict[str, Any]]:
    raw = hints.get("failures") or hints.get("jobs") or hints.get("blocked_jobs")
    fallback = [{"name": "no failed generation jobs", "reason": "none", "status": "clear", "profile": "all profiles"}]
    rows = unique_records(named(raw, ("job_id", "id", "template", "profile")), fallback)
    normalized = []
    for index, row in enumerate(rows, 1):
        reason = compact(row.get("reason") or row.get("failure_reason") or row.get("status")) or "unknown"
        normalized.append({**row, "id": compact(row.get("id") or row.get("job_id")) or f"SGF{index}", "reason": reason, "profile": compact(row.get("profile")) or "unknown profile", "template": compact(row.get("template") or row.get("spec_template")) or "unknown template"})
    return sorted(normalized, key=lambda row: (_reason_rank(row["reason"]), row["profile"].casefold(), row["template"].casefold(), compact(row["id"]).casefold()))


def _groups(failures: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for failure in failures:
        key = (failure["reason"], failure["profile"] if failure["profile"] != "unknown profile" else failure["template"])
        grouped.setdefault(key, []).append(failure)
    return [
        item("SGG", index, {"name": f"{reason} / {scope}", "reason": reason, "description": f"Recover {len(rows)} spec generation job(s) blocked by {reason} for {scope}."}, "spec_owner", evidence_ids, "Group spec generation failures", extra_keys=("reason",))
        | {"job_ids": [compact(row["id"]) for row in rows], "profile_or_template": scope, "failure_count": len(rows)}
        for index, ((reason, scope), rows) in enumerate(sorted(grouped.items(), key=lambda item: (_reason_rank(item[0][0]), item[0][1].casefold())), 1)
    ]


def _retry_order(groups: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("SGR", index, {"name": group["name"], "description": f"Retry after remediation for {group['profile_or_template']} with idempotent generation and captured logs."}, "generation_owner", evidence_ids, "Retry spec generation") | {"reason": group["reason"]} for index, group in enumerate(groups, 1)]


def _repair_actions(groups: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    actions = []
    for index, group in enumerate(groups, 1):
        reason = group["reason"].lower()
        if "evidence" in reason:
            description = "Attach missing evidence ids, regenerate evidence summaries, and block publication until references resolve."
        elif "input" in reason or "prompt" in reason:
            description = "Repair prompt variables, normalize inputs, and rerun template rendering before retry."
        elif "budget" in reason:
            description = "Do not retry until budget is reallocated or the job is rescheduled with a smaller generation scope."
        else:
            description = "Inspect failed logs, repair generation inputs, and rerun the job in priority order."
        actions.append(item("SGA", index, {"name": group["name"], "description": description}, "spec_owner", evidence_ids, "Repair spec generation input") | {"reason": group["reason"]})
    return actions


def _budget_checks(groups: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    has_budget = any("budget" in group["reason"].lower() for group in groups)
    record = {"name": "budget exhaustion remediation" if has_budget else "pre-retry budget check", "description": "Reallocate LLM budget, lower token scope, and require approval before retrying exhausted jobs." if has_budget else "Confirm retry budget, rate limits, and queue capacity before resubmitting generation jobs."}
    return [item("SGC", 1, record, "platform_owner", evidence_ids, "Check spec generation budget")]


def _reason_rank(reason: str) -> int:
    text = reason.lower()
    if "budget" in text:
        return 0
    if "evidence" in text:
        return 1
    if "input" in text or "prompt" in text:
        return 2
    if "transient" in text or "timeout" in text:
        return 3
    return 4
