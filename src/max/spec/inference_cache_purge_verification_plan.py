"""Generate deterministic inference cache purge verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.inference_cache_purge_verification_plan.v1"
KIND = "max.spec.inference_cache_purge_verification_plan"


def generate_inference_cache_purge_verification_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "inference_cache_purge_verification")
    caches = unique_records(
        named(
            hints.get("caches") or hints.get("cache_entries") or hints.get("inventories"),
            ("cache", "cache_key", "store", "region"),
        ),
        [
            {
                "name": "inference cache inventory",
                "owner": "ml_platform_owner",
                "severity": "medium",
                "scope": "all production inference caches",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, cache_count=len(caches)),
        "cache_inventories": [
            item(
                "ICP",
                index,
                record,
                "ml_platform_owner",
                evidence_ids,
                "Inventory inference cache entry",
                name_keys=("name", "cache", "cache_key", "store", "region"),
                extra_keys=("cache", "cache_key", "store", "region", "scope"),
            )
            for index, record in enumerate(caches, start=1)
        ],
        "purge_triggers": section(
            hints,
            ("purge_triggers", "triggers"),
            "ICT",
            "ml_platform_owner",
            "Define inference cache purge trigger",
            evidence_ids,
            [
                "model update, prompt policy change, tenant deletion, data correction, or safety incident"
            ],
        ),
        "data_scope": section(
            hints,
            ("data_scope", "customer_scope"),
            "ICD",
            "privacy_owner",
            "Constrain purge data scope",
            evidence_ids,
            ["customer, tenant, region, prompt hash, embedding namespace, and retention boundary"],
        ),
        "verification_evidence": section(
            hints,
            ("verification_evidence", "evidence"),
            "ICV",
            "compliance_owner",
            "Collect purge verification evidence",
            evidence_ids,
            ["before/after cache counts, sampled misses, audit logs, and purge job receipt"],
        ),
        "residual_risk_exceptions": section(
            hints,
            ("residual_risks", "exceptions"),
            "ICR",
            "risk_owner",
            "Review residual purge risk",
            evidence_ids,
            [
                "document retained replicas, delayed edge invalidation, or infeasible historical replay gaps"
            ],
        ),
        "replay_safeguards": section(
            hints,
            ("replay_safeguards", "rollback_controls"),
            "ICS",
            "platform_owner",
            "Safeguard rollback and replay",
            evidence_ids,
            ["disable stale cache rehydration, pin purge checkpoints, and validate replay inputs"],
        ),
        "approval_gates": section(
            hints,
            ("approvals", "approval_gates"),
            "ICA",
            "program_owner",
            "Gate inference cache purge verification",
            evidence_ids,
            [
                "ML platform, privacy, security, customer owner, and compliance approval before closure"
            ],
        ),
        "evidence_references": ctx["evidence_references"],
    }
