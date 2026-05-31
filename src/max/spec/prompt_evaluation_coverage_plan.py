"""Generate deterministic prompt evaluation coverage plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.prompt_evaluation_coverage_plan.v1"
KIND = "max.spec.prompt_evaluation_coverage_plan"


def generate_prompt_evaluation_coverage_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_evaluation_coverage")
    prompts = unique_records(named(hints.get("prompts") or hints.get("prompt_inventory"), ("prompt", "template", "name")), [{"name": "prompt coverage bootstrap", "coverage_status": "missing", "owner": "prompt_owner"}])
    prompts = sorted(prompts, key=lambda row: (_rank(row), compact(row.get("name")).casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Prompt Evaluation Coverage Plan", "summary": source_summary(ctx, prompt_count=len(prompts), uncovered_count=sum(1 for row in prompts if _rank(row) == 0)), "prompt_inventory": [item("PEC", i, row, "prompt_owner", evidence_ids, "Inventory prompt evaluation coverage", name_keys=("name", "prompt", "template"), extra_keys=("coverage_status", "next_refresh_date")) for i, row in enumerate(prompts, 1)], "scenario_coverage": section(hints, ("scenario_coverage", "scenarios"), "PES", "evaluation_owner", "Map prompt scenario coverage", evidence_ids, ["happy path, edge cases, safety cases, locale, tenant profile, and regression scenarios"]), "golden_set_links": section(hints, ("golden_set_links", "golden_sets"), "PEG", "evaluation_owner", "Link prompt golden set", evidence_ids, ["golden set id, version, owner, sample count, and refresh cadence"]), "risk_gaps": _gaps(prompts, evidence_ids), "owner_assignments": section(hints, ("owner_assignments", "owners"), "PEO", "prompt_owner", "Assign prompt coverage owner", evidence_ids, ["prompt owner, evaluator, workflow owner, and approval reviewer"]), "refresh_cadence": section(hints, ("refresh_cadence", "cadence"), "PER", "evaluation_owner", "Set prompt evaluation refresh cadence", evidence_ids, ["refresh after prompt changes, model changes, incidents, and scheduled quarterly review"]), "bootstrap_checklist": section(hints, ("bootstrap_checklist", "bootstrap"), "PEB", "evaluation_owner", "Bootstrap prompt evaluation coverage", evidence_ids, ["inventory prompts, assign owners, define scenarios, create golden sets, and schedule refresh"]), "evidence_references": ctx["evidence_references"]}


def _rank(row: dict[str, Any]) -> int:
    text = f"{compact(row.get('coverage_status'))} {compact(row.get('missing_scenarios'))}".lower()
    high = compact(row.get("risk")).lower() == "high" or compact(row.get("severity")).lower() == "high"
    return 0 if high and any(term in text for term in ("missing", "none", "uncovered", "gap")) else (1 if any(term in text for term in ("missing", "none", "uncovered", "gap")) else 2)


def _gaps(prompts: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("PEA", i, {"name": compact(row.get("name")), "severity": "high" if _rank(row) == 0 else "medium", "description": "Prioritize uncovered high-risk prompt with missing scenarios and golden-set gaps." if _rank(row) == 0 else "Close prompt evaluation coverage gaps and record owner plus next refresh date."}, "evaluation_owner", evidence_ids, "Close prompt evaluation coverage gap") for i, row in enumerate(prompts, 1)]
