"""Generate deterministic training dataset removal plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.training_dataset_removal_plan.v1"
KIND = "max.spec.training_dataset_removal_plan"


def generate_training_dataset_removal_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "training_dataset_removal")
    datasets = unique_records(
        named(
            hints.get("datasets")
            or hints.get("training_datasets")
            or hints.get("dataset_removals"),
            ("dataset", "source", "reason"),
        ),
        [
            {
                "name": "flagged training dataset",
                "source": "model training store",
                "reason": "policy, consent, quality, or licensing removal trigger",
                "owner": "data_owner",
                "due_at": "before next training run",
                "severity": "high",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, dataset_count=len(datasets)),
        "datasets": [
            item(
                "TDR",
                index,
                record,
                "data_owner",
                evidence_ids,
                "Remove training dataset",
                name_keys=("name", "dataset", "source", "reason"),
                extra_keys=("dataset", "source", "reason", "due_at"),
            )
            for index, record in enumerate(datasets, start=1)
        ],
        "removal_triggers": section(
            hints,
            ("removal_triggers", "triggers", "reasons"),
            "TDT",
            "data_governance_owner",
            "Define dataset removal trigger",
            evidence_ids,
            ["consent withdrawal, license expiry, data quality failure, or policy violation"],
        ),
        "downstream_impact": section(
            hints,
            ("downstream_impact", "model_impact", "impacted_models"),
            "TDI",
            "model_owner",
            "Assess downstream model impact",
            evidence_ids,
            [
                "identify trained models, evaluation baselines, embeddings, caches, and "
                "customer-facing outputs affected by the dataset"
            ],
        ),
        "removal_steps": section(
            hints,
            ("removal_steps", "steps", "quarantine_steps", "retraining_steps"),
            "TDS",
            "ml_platform_owner",
            "Remove, quarantine, or retrain from dataset",
            evidence_ids,
            [
                "freeze affected training runs, quarantine dataset shards, rebuild derived "
                "features, and schedule retraining if needed"
            ],
        ),
        "verification_plan": section(
            hints,
            ("verification_plan", "verification", "evidence"),
            "TDV",
            "quality_owner",
            "Verify dataset removal evidence",
            evidence_ids,
            ["storage deletion receipt, lineage query, retraining manifest, and reviewer signoff"],
        ),
        "owner_matrix": section(
            hints,
            ("owner_matrix", "owners", "approvers"),
            "TDO",
            "program_owner",
            "Assign dataset removal owner",
            evidence_ids,
            ["data owner, model owner, privacy reviewer, security reviewer, and release manager"],
        ),
        "timeline": section(
            hints,
            ("timeline", "milestones", "schedule"),
            "TDM",
            "program_owner",
            "Track dataset removal timeline",
            evidence_ids,
            [
                "triage, quarantine, removal, retraining, verification, and release "
                "decision milestones"
            ],
        ),
        "rollback_plan": section(
            hints,
            ("rollback_plan", "rollback", "backout"),
            "TDX",
            "release_manager",
            "Rollback dataset removal change",
            evidence_ids,
            [
                "restore last approved model artifact and keep removed dataset quarantined "
                "pending governance review"
            ],
        ),
        "evidence_references": ctx["evidence_references"],
    }
