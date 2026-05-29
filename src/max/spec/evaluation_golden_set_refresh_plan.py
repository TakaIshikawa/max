"""Generate deterministic evaluation golden set refresh plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.evaluation_golden_set_refresh_plan.v1"
KIND = "max.spec.evaluation_golden_set_refresh_plan"


def generate_evaluation_golden_set_refresh_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "evaluation_golden_set_refresh")
    datasets = unique_records(named(hints.get("dataset_inventory") or hints.get("datasets"), ("dataset", "name")), [{"name": "primary evaluation golden set", "owner": "evaluation_owner"}])
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Evaluation Golden Set Refresh Plan", "summary": source_summary(ctx, dataset_count=len(datasets)), "dataset_inventory": [item("EGD", i, r, "evaluation_owner", evidence_ids, "Inventory evaluation golden set", extra_keys=("version", "sample_count")) for i, r in enumerate(datasets, 1)], "refresh_triggers": section(hints, ("refresh_triggers", "triggers"), "EGT", "evaluation_owner", "Define refresh trigger", evidence_ids, ["score drift, stale examples, product behavior change, or evaluator disagreement"]), "sampling_strategy": section(hints, ("sampling_strategy", "sampling"), "EGS", "evaluation_owner", "Define sampling strategy", evidence_ids, ["stratify by profile, task, difficulty, language, and failure mode"]), "labeling_guidelines": section(hints, ("labeling_guidelines", "guidelines"), "EGL", "labeling_owner", "Refresh labeling guideline", evidence_ids, ["calibrate labels with gold examples and adjudication rules"]), "regression_checks": section(hints, ("regression_checks", "checks"), "EGR", "evaluation_owner", "Run regression check", evidence_ids, ["compare old and refreshed golden scores before rollout"]), "rollout_steps": section(hints, ("rollout_steps", "rollout"), "EGO", "evaluation_owner", "Roll out golden refresh", evidence_ids, ["version dataset, rerun baseline, publish changelog, archive prior set"]), "rollback_criteria": section(hints, ("rollback_criteria", "rollback"), "EGB", "evaluation_owner", "Define rollback criteria", evidence_ids, ["rollback if score variance or labeling defects exceed tolerance"]), "signoff": section(hints, ("signoff", "approvers"), "EGA", "evaluation_owner", "Approve golden set refresh", evidence_ids, ["evaluation owner and model owner signoff"]), "evidence_references": ctx["evidence_references"]}
