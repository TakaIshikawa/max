"""Generate deterministic fine-tuning job cancellation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.fine_tuning_job_cancellation_plan.v1"
KIND = "max.spec.fine_tuning_job_cancellation_plan"


def generate_fine_tuning_job_cancellation_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "fine_tuning_job_cancellation")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    jobs = unique_records(
        named(
            hints.get("jobs") or hints.get("job_identifiers") or hints.get("fine_tuning_jobs"),
            ("job_id", "provider", "model", "run_id"),
        ),
        [
            {
                "name": "fine-tuning job identifier required",
                "provider": compact(hints.get("provider")) or "provider-required",
                "job_id": compact(hints.get("job_id") or hints.get("fine_tuning_job_id"))
                or "job-id-required",
                "owner": "ml_platform_owner",
                "severity": "high",
            }
        ],
    )
    blockers = _blockers(jobs, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, job_count=len(jobs), blocker_count=len(blockers)),
        "job_identifiers": [
            item(
                "FTJ",
                index,
                record,
                "ml_platform_owner",
                evidence_ids,
                "Identify fine-tuning job to cancel",
                name_keys=("name", "job_id", "run_id", "provider", "model"),
                extra_keys=("provider", "job_id", "run_id", "model", "region", "status"),
            )
            for index, record in enumerate(jobs, start=1)
        ],
        "cancellation_triggers": _named_section(
            hints,
            ("cancellation_triggers", "triggers", "conditions"),
            ("trigger", "condition", "risk", "scenario"),
            "FTC",
            "model_owner",
            "Trigger fine-tuning job cancellation",
            evidence_ids,
            [
                "policy violation, bad training data, runaway cost, stalled job, or failed safety gate"
            ],
            name_keys=("name", "trigger", "condition", "risk", "description"),
            extra_keys=("trigger", "condition", "risk", "threshold"),
        ),
        "rollback_steps": section(
            hints,
            ("rollback_steps", "rollback", "rollback_plan"),
            "FTR",
            "ml_platform_owner",
            "Rollback fine-tuning job side effects",
            evidence_ids,
            [
                "cancel provider job, disable promoted artifacts, restore prior model routing, "
                "and record rollback decision"
            ],
        ),
        "checkpoint_handling": section(
            hints,
            ("checkpoint_handling", "checkpoint_disposition", "checkpoints"),
            "FTH",
            "model_owner",
            "Handle fine-tuning checkpoints",
            evidence_ids,
            [
                "quarantine partial checkpoints, prevent promotion, retain hashes, and expire unusable artifacts"
            ],
            extra_keys=("checkpoint_id", "disposition", "retention", "expiry"),
        ),
        "dataset_cleanup": section(
            hints,
            ("dataset_cleanup", "cleanup_steps", "data_cleanup", "datasets"),
            "FTD",
            "data_owner",
            "Clean up fine-tuning dataset artifacts",
            evidence_ids,
            [
                "revoke temporary dataset access, purge staging files, remove derived shards, "
                "and preserve deletion evidence"
            ],
            extra_keys=("dataset", "location", "retention", "status"),
        ),
        "cost_controls": section(
            hints,
            ("cost_controls", "cost_cap", "budget", "spend_controls"),
            "FTB",
            "finance_owner",
            "Enforce fine-tuning cancellation cost control",
            evidence_ids,
            [
                "stop training spend, cap provider charges, alert finance owner, and reconcile final invoice"
            ],
            name_keys=("name", "cost_cap", "budget", "threshold", "description"),
            extra_keys=("cost_cap", "budget", "threshold", "currency"),
        ),
        "stakeholder_notification": section(
            hints,
            ("stakeholder_notification", "notifications", "communications"),
            "FTN",
            "program_owner",
            "Notify fine-tuning cancellation stakeholders",
            evidence_ids,
            [
                "notify model owner, data owner, finance owner, support, and affected workflow owners"
            ],
            name_keys=("name", "channel", "recipient", "audience", "description"),
            extra_keys=("channel", "recipient", "audience", "deadline"),
        ),
        "post_cancel_validation": section(
            hints,
            ("post_cancel_validation", "validation", "validation_checks"),
            "FTV",
            "quality_owner",
            "Validate fine-tuning cancellation completion",
            evidence_ids,
            [
                "provider job is cancelled, no checkpoint is routable, dataset staging is clean, "
                "cost alert is closed, and rollback route passes smoke tests"
            ],
        ),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(jobs: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for record in jobs:
        provider = compact(record.get("provider"))
        job_id = compact(
            record.get("job_id") or record.get("fine_tuning_job_id") or record.get("run_id")
        )
        if not provider or provider == "provider-required":
            blockers.append(
                item(
                    "FTK",
                    len(blockers) + 1,
                    {"name": "missing provider identifier", "severity": "high", "job_id": job_id},
                    "ml_platform_owner",
                    evidence_ids,
                    "Resolve fine-tuning cancellation blocker",
                    extra_keys=("job_id",),
                )
            )
        if not job_id or job_id == "job-id-required":
            blockers.append(
                item(
                    "FTK",
                    len(blockers) + 1,
                    {
                        "name": "missing fine-tuning job identifier",
                        "severity": "high",
                        "provider": provider,
                    },
                    "ml_platform_owner",
                    evidence_ids,
                    "Resolve fine-tuning cancellation blocker",
                    extra_keys=("provider",),
                )
            )
    return blockers


def _named_section(
    hints: dict[str, Any],
    keys: tuple[str, ...],
    aliases: tuple[str, ...],
    prefix: str,
    owner: str,
    label: str,
    evidence_ids: list[str],
    fallback: list[Any],
    *,
    name_keys: tuple[str, ...] = ("name", "title", "id", "description"),
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return section(
        {"value": named(value, aliases)},
        ("value",),
        prefix,
        owner,
        label,
        evidence_ids,
        fallback,
        name_keys=name_keys,
        extra_keys=extra_keys,
    )
