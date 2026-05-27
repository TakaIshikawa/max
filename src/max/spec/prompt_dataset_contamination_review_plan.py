"""Generate deterministic prompt dataset contamination review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.prompt_dataset_contamination_review_plan.v1"
KIND = "max.spec.prompt_dataset_contamination_review_plan"


def generate_prompt_dataset_contamination_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_dataset_contamination_review")
    examples = unique_records(
        named(hints.get("affected_examples") or hints.get("examples") or hints.get("prompts"), ("prompt_id", "dataset", "id")),
        [{"name": "suspect prompt example", "prompt_id": "suspect prompt example", "severity": "medium"}],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Prompt Dataset Contamination Review Plan",
        "summary": source_summary(ctx, affected_example_count=len(examples), reviewer_count=len(_reviewers(hints))),
        "contamination_summary": section(
            hints,
            ("contamination_summary", "summary_items", "contamination_indicators"),
            "PDC",
            "data_governance_owner",
            "Summarize prompt dataset contamination",
            evidence_ids,
            ["review contamination source, affected dataset, overlap indicator, and expected evaluation bias"],
            extra_keys=("dataset", "contamination_source", "indicator", "risk"),
        ),
        "affected_examples": [
            item(
                "PDE",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Review affected prompt example",
                name_keys=("name", "prompt_id", "id", "dataset"),
                extra_keys=("dataset", "prompt_id", "contamination_source", "reviewer"),
            )
            for index, record in enumerate(examples, start=1)
        ],
        "quarantine_steps": section(
            hints,
            ("quarantine_steps", "quarantine", "isolation_steps"),
            "PDQ",
            "data_governance_owner",
            "Quarantine contaminated prompt data",
            evidence_ids,
            ["remove examples from active evals, freeze dataset version, restrict access, and label lineage"],
        ),
        "replacement_sampling_plan": section(
            hints,
            ("replacement_sampling_plan", "replacement_sampling", "sampling_plan"),
            "PDR",
            "evaluation_owner",
            "Sample replacement prompt data",
            evidence_ids,
            ["draw fresh examples by task, locale, difficulty, customer segment, and safety category"],
            extra_keys=("dataset", "sample_size", "strata"),
        ),
        "approval_gates": section(
            hints,
            ("approval_gates", "approvals", "signoff"),
            "PDA",
            "program_owner",
            "Approve prompt dataset contamination review",
            evidence_ids,
            ["dataset owner, evaluation owner, policy owner, and release manager approval before reuse"],
            extra_keys=("reviewer", "decision", "deadline"),
        ),
        "reviewers": [
            item(
                "PDV",
                index,
                record,
                "program_owner",
                evidence_ids,
                "Assign contamination reviewer",
                name_keys=("name", "reviewer", "role"),
                extra_keys=("reviewer", "role", "team"),
            )
            for index, record in enumerate(_reviewers(hints), start=1)
        ],
        "audit_evidence": section(
            hints,
            ("audit_evidence", "evidence", "audit_trail"),
            "PDT",
            "audit_owner",
            "Collect prompt contamination audit evidence",
            evidence_ids,
            ["dataset version diff, quarantine log, replacement sample manifest, approvals, and rerun results"],
            extra_keys=("artifact", "location", "artifact_owner"),
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _reviewers(hints: dict[str, Any]) -> list[dict[str, Any]]:
    return unique_records(
        named(hints.get("reviewers") or hints.get("approvers") or hints.get("owners"), ("reviewer", "role")),
        [{"name": "evaluation owner", "reviewer": "evaluation owner", "role": "review approver"}],
    )
