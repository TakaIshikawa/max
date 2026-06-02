"""Generate deterministic synthetic signal poisoning response plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, summary
from max.spec._review_plan_common import base, ordered, row, values

SCHEMA_VERSION = "max.spec.synthetic_signal_poisoning_response_plan.v1"
KIND = "max.spec.synthetic_signal_poisoning_response_plan"


def generate_synthetic_signal_poisoning_response_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "synthetic_signal_poisoning_response")
    _require(hints, ("source", "poisoning_indicator", "affected_signal_ids", "detected_at", "owner"))
    source = compact(hints["source"])
    owner = compact(hints["owner"])
    signals = values(hints.get("affected_signal_ids"), [])
    quarantine_actions = values(hints.get("quarantine_actions"), ["quarantine affected signals", "disable synthetic source ingestion"])
    retraining_impacts = values(hints.get("retraining_impacts"), ["review training and evaluation sets for poisoned signal inclusion"])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, source=source, poisoning_indicator=compact(hints["poisoning_indicator"]), detected_at=compact(hints["detected_at"]), affected_signal_count=len(signals)),
        "quarantine": [row("SSPQ", index, action, owner, f"Quarantine poisoning path for {source}: {action}.", evidence_ids) for index, action in enumerate(quarantine_actions, 1)],
        "affected_signals": [row("SSPS", index, signal_id, owner, f"Preserve and inspect affected synthetic signal {signal_id}.", evidence_ids, signal_id=signal_id) for index, signal_id in enumerate(signals, 1)],
        "investigation": [row("SSPI", 1, "Poisoning indicator investigation", owner, f"Trace {compact(hints['poisoning_indicator'])} across source generation, ingestion, and review logs.", evidence_ids)],
        "downstream_impact": [
            row("SSPD", 1, "Insights check", owner, "Identify generated insights influenced by affected synthetic signals.", evidence_ids, artifact="insights"),
            row("SSPD", 2, "Units check", owner, "Identify buildable units influenced by affected synthetic signals.", evidence_ids, artifact="units"),
            row("SSPD", 3, "Generated specs check", owner, "Identify generated specs influenced by affected synthetic signals.", evidence_ids, artifact="generated_specs"),
        ],
        "remediation": [row("SSPR", index, impact, owner, f"Remediate retraining impact: {impact}.", evidence_ids) for index, impact in enumerate(retraining_impacts, 1)],
        "prevention": [row("SSPP", 1, "Poisoning prevention gate", owner, f"Add source validation and review-window checks for {compact(hints.get('review_window_days')) or 'configured'} days.", evidence_ids)],
        "evidence_references": ctx["evidence_references"],
    }


def _require(hints: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not values(hints.get(key), [])]
    if missing:
        raise ValueError(f"Missing synthetic signal poisoning response fields: {', '.join(ordered(missing))}")
