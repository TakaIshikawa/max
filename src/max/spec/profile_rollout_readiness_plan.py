"""Generate deterministic profile rollout readiness plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary

SCHEMA_VERSION = "max.spec.profile_rollout_readiness_plan.v1"
KIND = "max.spec.profile_rollout_readiness_plan"


def generate_profile_rollout_readiness_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    profile = compact(hints.get("profile") or hints.get("profile_name") or spec.get("profile") or spec.get("profile_name")) or "unnamed profile"
    owners = _values(hints.get("owners") or spec.get("owners"))
    sources = _values(hints.get("source_mix") or hints.get("sources") or spec.get("source_mix"))
    constraints = _values(hints.get("changed_constraints") or spec.get("changed_constraints"))
    gaps = _readiness_gaps(owners, sources)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, profile=profile, readiness_status="blocked" if gaps else "ready", readiness_gap_count=len(gaps)),
        "readiness_checklist": _checklist(profile, owners, sources, constraints),
        "readiness_gaps": gaps,
        "dry_run_validation": _dry_runs(profile),
        "risk_register": _risks(profile, constraints, sources, owners),
        "monitoring_metrics": _monitoring_metrics(),
        "approval_gates": _approval_gates(owners),
        "rollback_criteria": _rollback_criteria(profile),
        "evidence_references": ctx["evidence_references"],
    }


def _checklist(profile: str, owners: list[str], sources: list[str], constraints: list[str]) -> list[dict[str, Any]]:
    items = [
        ("PRC1", "profile_definition", f"Document launch scope for {profile}.", bool(profile != "unnamed profile")),
        ("PRC2", "source_coverage", "Confirm source mix covers required domains and freshness windows.", bool(sources)),
        ("PRC3", "evaluation_weights", "Review evaluation weights against profile goals and constraint changes.", True),
        ("PRC4", "constraint_review", "Validate changed constraints for conflicts and unsupported states.", True),
        ("PRC5", "owner_coverage", "Assign product, research, evaluation, and operations owners.", bool(owners)),
    ]
    return [{"id": item_id, "name": name, "description": desc, "complete": complete, "references": constraints if name == "constraint_review" else []} for item_id, name, desc, complete in items]


def _readiness_gaps(owners: list[str], sources: list[str]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not owners:
        gaps.append({"id": "PRG1", "type": "missing_owner", "severity": "high", "description": "No rollout owners were supplied."})
    if not sources:
        gaps.append({"id": "PRG2", "type": "missing_source_mix", "severity": "high", "description": "No source mix or coverage data was supplied."})
    return gaps


def _dry_runs(profile: str) -> list[dict[str, str]]:
    return [
        {"id": "PRD1", "name": "source_query_replay", "action": f"Replay source queries for {profile} against recent signals."},
        {"id": "PRD2", "name": "evaluation_weight_check", "action": "Run golden examples through proposed weights and compare approval distribution."},
        {"id": "PRD3", "name": "constraint_failure_probe", "action": "Exercise changed constraints with known pass, fail, and edge-case examples."},
    ]


def _risks(profile: str, constraints: list[str], sources: list[str], owners: list[str]) -> list[dict[str, str]]:
    risks = [
        {"id": "PRR1", "name": "coverage_gap", "severity": "high" if not sources else "medium", "mitigation": "Add source coverage before approving rollout."},
        {"id": "PRR2", "name": "constraint_regression", "severity": "medium" if constraints else "low", "mitigation": "Compare constraint outcomes against prior profile behavior."},
        {"id": "PRR3", "name": "ownership_gap", "severity": "high" if not owners else "low", "mitigation": f"Assign accountable owners for {profile}."},
    ]
    return risks


def _monitoring_metrics() -> list[dict[str, str]]:
    return [
        {"id": "PRM1", "name": "source_coverage_rate", "target": ">= 95% required source coverage"},
        {"id": "PRM2", "name": "approval_rate_delta", "target": "within agreed launch tolerance"},
        {"id": "PRM3", "name": "constraint_violation_rate", "target": "0 critical violations"},
    ]


def _approval_gates(owners: list[str]) -> list[dict[str, Any]]:
    owner = owners[0] if owners else "unassigned"
    return [
        {"id": "PRA1", "name": "profile_owner_signoff", "owner": owner, "required": True},
        {"id": "PRA2", "name": "evaluation_owner_signoff", "owner": "evaluation_owner", "required": True},
        {"id": "PRA3", "name": "operations_launch_signoff", "owner": "operations_owner", "required": True},
    ]


def _rollback_criteria(profile: str) -> list[dict[str, str]]:
    return [
        {"id": "PRB1", "name": "critical_constraint_failure", "action": f"Disable {profile} rollout and restore previous profile configuration."},
        {"id": "PRB2", "name": "source_coverage_drop", "action": "Rollback if required source coverage drops below threshold for two checks."},
    ]


def _values(value: Any) -> list[str]:
    return sorted(set(string_list(value)), key=str.casefold)


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("profile_rollout_readiness")
    return hints if isinstance(hints, dict) else {}
