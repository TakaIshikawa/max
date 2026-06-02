"""Generate deterministic profile launch rollback plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, summary
from max.spec._review_plan_common import base, ordered, row, values

SCHEMA_VERSION = "max.spec.profile_launch_rollback_plan.v1"
KIND = "max.spec.profile_launch_rollback_plan"


def generate_profile_launch_rollback_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "profile_launch_rollback")
    _require(hints, ("profile", "launch_version", "rollback_version", "launch_owner", "rollback_triggers"))
    owner = compact(hints["launch_owner"])
    profile = compact(hints["profile"])
    triggers = values(hints.get("rollback_triggers"), [])
    validation_checks = values(hints.get("validation_checks"), ["profile output parity", "source freshness"])
    sources = values(hints.get("affected_sources"), ["affected source inventory"])
    channels = values(hints.get("communication_channels"), ["launch channel"])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, profile=profile, launch_version=compact(hints["launch_version"]), rollback_version=compact(hints["rollback_version"]), trigger_count=len(triggers)),
        "trigger_review": [row("PLRT", index, trigger, owner, f"Evaluate rollback trigger for {profile}: {trigger}.", evidence_ids) for index, trigger in enumerate(triggers, 1)],
        "rollback_execution": [row("PLRE", 1, "Execute profile rollback", owner, f"Move {profile} from {compact(hints['launch_version'])} to {compact(hints['rollback_version'])}.", evidence_ids, required=True)],
        "source_validation": [row("PLRS", index, source, owner, f"Validate source behavior after rollback: {source}.", evidence_ids) for index, source in enumerate(sources, 1)],
        "validation_checks": [row("PLRV", index, check, owner, f"Confirm rollback validation check: {check}.", evidence_ids) for index, check in enumerate(validation_checks, 1)],
        "stakeholder_communication": [row("PLRC", index, channel, owner, f"Send rollback status through {channel}.", evidence_ids) for index, channel in enumerate(channels, 1)],
        "relaunch_criteria": [row("PLRR", 1, "Relaunch approval criteria", owner, "Require trigger closure, source validation, stakeholder acknowledgement, and release owner approval before relaunch.", evidence_ids, required=True)],
        "evidence_references": ctx["evidence_references"],
    }


def _require(hints: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not values(hints.get(key), [])]
    if missing:
        raise ValueError(f"Missing profile launch rollback fields: {', '.join(ordered(missing))}")
