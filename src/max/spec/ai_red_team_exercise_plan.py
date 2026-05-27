"""Generate deterministic AI red team exercise plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, rank, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.ai_red_team_exercise_plan.v1"
KIND = "max.spec.ai_red_team_exercise_plan"


def generate_ai_red_team_exercise_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "ai_red_team_exercise")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    scenarios = sorted(
        unique_records(
            named(hints.get("attack_scenarios") or hints.get("scenarios"), ("scenario", "name")),
            [{"name": "prompt injection", "severity": "high", "owner": "ai_safety_owner"}],
        ),
        key=lambda record: (rank(record.get("severity")), compact(record.get("name")).casefold()),
    )
    scenario_rows = [_scenario("ART", index, record, evidence_ids) for index, record in enumerate(scenarios, start=1)]
    blockers = _exercise_blockers(hints, scenario_rows, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "AI Red Team Exercise Plan",
        "summary": source_summary(ctx, scenario_count=len(scenario_rows), blocker_count=len(blockers)),
        "scope": section(hints, ("scope", "model_feature_scope"), "ARS", "product_owner", "Confirm AI red team scope", evidence_ids, ["models, tools, policies, launch surface, and excluded systems"]),
        "attack_scenarios": scenario_rows,
        "safety_boundaries": section(hints, ("safety_boundaries", "boundaries"), "ARB", "ai_safety_owner", "Define red team safety boundary", evidence_ids, []),
        "required_participants": section(hints, ("required_participants", "participants"), "ARP", "program_owner", "Assign red team participant", evidence_ids, ["AI safety lead, security tester, model owner, policy reviewer, and incident commander"]),
        "evidence_capture": section(hints, ("evidence_capture", "evidence"), "ARE", "ai_safety_owner", "Capture red team evidence", evidence_ids, ["prompt transcript, model output, policy label, severity, owner, and remediation link"]),
        "remediation_tracking": section(hints, ("remediation_tracking", "remediations"), "ARR", "ai_safety_owner", "Track red team remediation", evidence_ids, ["owner, due date, mitigation status, validation run, and residual risk"]),
        "exit_criteria": section(hints, ("exit_criteria", "completion"), "ARX", "program_owner", "Confirm red team exit criteria", evidence_ids, ["critical findings remediated or risk accepted, evidence archived, and approvers signed off"]),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _scenario(prefix: str, index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    data = item(prefix, index, record, "ai_safety_owner", evidence_ids, "Run AI red team attack scenario", name_keys=("name", "scenario"), extra_keys=("target", "technique", "remediation_owner", "evidence_id"))
    if isinstance(record.get("metadata"), dict):
        data["metadata"] = dict(sorted(record["metadata"].items()))
    return data


def _exercise_blockers(hints: dict[str, Any], scenarios: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not hints.get("safety_boundaries") and not hints.get("boundaries"):
        blockers.append(row("ARBK", len(blockers) + 1, "missing safety boundaries", "ai_safety_owner", "AI red team exercise must define safety boundaries before execution.", evidence_ids, severity="critical"))
    for scenario in scenarios:
        if not compact(scenario.get("remediation_owner")):
            blockers.append(row("ARBK", len(blockers) + 1, f"missing remediation owner for {scenario['name']}", "ai_safety_owner", "Scenario must have an accountable remediation owner.", evidence_ids, severity="high", scenario=scenario["name"]))
    return blockers
