"""Generate deterministic event schema evolution plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.event_schema_evolution_plan.v1"
KIND = "max.spec.event_schema_evolution_plan"


def generate_event_schema_evolution_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "event_schema_evolution")
    event = compact(hints.get("event") or hints.get("event_name")) or "domain event"
    mode = compact(hints.get("compatibility_mode")) or "backward-compatible"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, event=event, compatibility_mode=mode),
        "producer_impact": section(hints, ("producers", "producer_impact"), "ESE", "producer_owner", "Update event producer", evidence_ids, ["primary producer"]),
        "consumer_impact": section(hints, ("consumers", "consumer_impact"), "ESC", "consumer_owner", "Validate event consumer", evidence_ids, ["primary consumer", "analytics consumer", "archive consumer"]),
        "compatibility": {"mode": mode, "event": event, "owner": compact(hints.get("owner")) or "event_platform_owner"},
        "dual_write_or_read_steps": section(hints, ("dual_write_steps", "dual_read_steps", "dual_write_or_read_steps"), "ESD", "engineering_owner", "Run dual-write or dual-read step", evidence_ids, ["emit old and new fields", "consume both versions", "compare payload parity"]),
        "validation_events": section(hints, ("validation_events", "validation"), "ESV", "qa_owner", "Validate evolved event", evidence_ids, ["golden event fixtures, schema registry checks, consumer contract tests"]),
        "replay_strategy": section(hints, ("replay_strategy", "replay"), "ESR", "data_platform_owner", "Replay event safely", evidence_ids, ["bounded replay window with idempotency and DLQ monitoring"]),
        "rollout_phases": section(hints, ("rollout_phases", "rollout"), "ESP", "release_owner", "Roll out event schema", evidence_ids, ["schema publish", "producer canary", "consumer migration", "legacy field deprecation"]),
        "rollback": section(hints, ("rollback",), "ESB", "on_call_owner", "Rollback event schema evolution", evidence_ids, ["disable new fields and replay from stable checkpoint"]),
        "deprecation_timeline": section(hints, ("deprecation_timeline", "deprecation"), "EST", "program_owner", "Deprecate old event schema", evidence_ids, ["announce timeline, monitor usage, remove legacy fields after gates pass"]),
        "evidence_references": ctx["evidence_references"],
    }
