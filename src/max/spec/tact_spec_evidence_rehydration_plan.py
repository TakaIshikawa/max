"""Generate deterministic Tact spec evidence rehydration plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, summary
from max.spec._review_plan_common import base, ordered, row, values

SCHEMA_VERSION = "max.spec.tact_spec_evidence_rehydration_plan.v1"
KIND = "max.spec.tact_spec_evidence_rehydration_plan"


def generate_tact_spec_evidence_rehydration_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "tact_spec_evidence_rehydration")
    _require(hints)
    owner = compact(hints["owner"])
    spec_id = compact(hints["spec_id"])
    missing = values(hints.get("missing_evidence_ids"), [])
    stale = values(hints.get("stale_evidence_ids"), [])
    sources = values(hints.get("source_systems"), [])
    steps = values(hints.get("rehydration_steps"), ["replay source evidence", "attach refreshed evidence to spec"])
    checks = values(hints.get("validation_checks"), ["evidence link resolves", "spec references refreshed evidence"])

    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, spec_id=spec_id, missing_evidence_count=len(missing), stale_evidence_count=len(stale), publication_blocked=bool(hints.get("publication_blocked"))),
        "evidence_lookup": [
            row("TSLM", index, evidence_id, owner, f"Locate missing evidence {evidence_id} before stale evidence review.", evidence_ids, evidence_id=evidence_id, priority="missing")
            for index, evidence_id in enumerate(missing, 1)
        ]
        + [
            row("TSLS", index, evidence_id, owner, f"Refresh stale evidence {evidence_id} after missing evidence lookup.", evidence_ids, evidence_id=evidence_id, priority="stale")
            for index, evidence_id in enumerate(stale, 1)
        ],
        "source_replay": [row("TSR", index, source, owner, f"Replay evidence from source system {source} for {spec_id}.", evidence_ids, source_system=source) for index, source in enumerate(sources, 1)],
        "rehydration_steps": [row("TSH", index, step, owner, f"Execute evidence rehydration step: {step}.", evidence_ids) for index, step in enumerate(steps, 1)],
        "validation": [row("TSV", index, check, owner, f"Validate rehydrated evidence: {check}.", evidence_ids) for index, check in enumerate(checks, 1)],
        "spec_update": [row("TSU", 1, "Spec evidence update", owner, f"Update {spec_id} with refreshed evidence references and audit notes.", evidence_ids, required=True)],
        "publication_unblock": [],
        "evidence_references": ctx["evidence_references"],
    }
    if hints.get("publication_blocked"):
        plan["publication_unblock"] = [row("TSB", 1, "Publication unblock approval", owner, "Approve publication unblock after evidence lookup, replay, validation, and spec update complete.", evidence_ids, required=True)]
    return plan


def _require(hints: dict[str, Any]) -> None:
    missing = [key for key in ("spec_id", "source_systems", "owner") if not values(hints.get(key), [])]
    if not values(hints.get("missing_evidence_ids"), []) and not values(hints.get("stale_evidence_ids"), []):
        missing.append("missing_evidence_ids or stale_evidence_ids")
    if missing:
        raise ValueError(f"Missing Tact spec evidence rehydration fields: {', '.join(ordered(missing))}")
