"""Generate deterministic release communications readiness plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records, values


SCHEMA_VERSION = "max.spec.release_communications_readiness_plan.v1"
KIND = "max.spec.release_communications_readiness_plan"


def generate_release_communications_readiness_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "release_communications_readiness")
    audiences = values(
        hints.get("audiences") or hints.get("audience_segments"), [ctx["target_user"]]
    )
    messages = unique_records(
        hints.get("message_variants") or hints.get("messages"),
        [
            {
                "name": "primary release message",
                "owner": "communications_owner",
                "description": "Prepare release message for the primary audience.",
            }
        ],
    )
    channels = values(
        hints.get("channels") or hints.get("send_channels"), ["email", "in-app message"]
    )
    approvals = unique_records(
        hints.get("approval_owners") or hints.get("approvals"),
        [
            {
                "name": "communications approval",
                "owner": "communications_owner",
                "description": "Approve message variants, channels, timing, and accessibility.",
            }
        ],
    )
    timing = unique_records(
        hints.get("timing_gates") or hints.get("timing"),
        [
            {
                "name": "release send gate",
                "owner": "release_owner",
                "description": "Send communications after release readiness and support briefing are complete.",
            }
        ],
    )
    localization = unique_records(
        hints.get("localization_accessibility_needs")
        or hints.get("localization")
        or hints.get("accessibility"),
        [
            {
                "name": "default localization and accessibility check",
                "owner": "localization_owner",
                "description": "Confirm release communications meet localization and accessibility needs.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "communications readiness validation",
                "owner": "communications_owner",
                "description": "Validate audiences, messages, channels, approvals, timing, localization, and accessibility.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            audience_count=len(audiences),
            message_variant_count=len(messages),
            channel_count=len(channels),
        ),
        "audiences": [
            _named("AUD", index, item, "customer_success_owner", evidence_ids)
            for index, item in enumerate(audiences, start=1)
        ],
        "message_variants": [
            _item("MSG", index, item, "communications_owner", evidence_ids)
            for index, item in enumerate(messages, start=1)
        ],
        "channels": [
            _named("CH", index, item, "communications_owner", evidence_ids)
            for index, item in enumerate(channels, start=1)
        ],
        "approval_owners": [
            _item("APP", index, item, "communications_owner", evidence_ids)
            for index, item in enumerate(approvals, start=1)
        ],
        "timing_gates": [
            _item("TIME", index, item, "release_owner", evidence_ids)
            for index, item in enumerate(timing, start=1)
        ],
        "localization_accessibility_needs": [
            _item("LOC", index, item, "localization_owner", evidence_ids)
            for index, item in enumerate(localization, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "communications_owner", evidence_ids)
            for index, item in enumerate(checks, start=1)
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _named(
    prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(prefix, index, name, owner, name, evidence_ids)


def _item(
    prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(
        prefix,
        index,
        compact(item.get("name")),
        compact(item.get("owner")) or owner,
        compact(item.get("description"))
        or compact(item.get("message"))
        or compact(item.get("name")),
        evidence_ids,
        severity=item.get("severity"),
        status=item.get("status"),
        timing=item.get("timing") or item.get("due") or item.get("deadline"),
    )
