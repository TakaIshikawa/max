"""Generate deterministic LLM vendor incident communication plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.llm_vendor_incident_communication_plan.v1"
KIND = "max.spec.llm_vendor_incident_communication_plan"
HIGH_SEVERITIES = {"critical", "high", "sev1", "sev2"}


def generate_llm_vendor_incident_communication_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "llm_vendor_incident_communication")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    incidents = unique_records(
        named(
            hints.get("incidents") or hints.get("incident_summary") or hints.get("providers"),
            ("provider", "incident", "summary"),
        ),
        [
            {
                "name": "LLM vendor incident",
                "provider": compact(hints.get("provider")) or "affected-provider-required",
                "severity": compact(hints.get("severity")) or "medium",
                "owner": "incident_commander",
            }
        ],
    )
    severity = _highest_severity(incidents)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, incident_count=len(incidents), severity=severity),
        "incident_summary": [
            item(
                "LVI",
                index,
                record,
                "incident_commander",
                evidence_ids,
                "Summarize LLM vendor incident",
                name_keys=("name", "incident", "summary", "provider"),
                extra_keys=("provider", "severity", "status", "started_at"),
            )
            for index, record in enumerate(incidents, start=1)
        ],
        "affected_stages": section(
            hints,
            ("affected_stages", "stages", "workflows"),
            "LVS",
            "platform_owner",
            "Identify affected LLM workflow stage",
            evidence_ids,
            [
                "synthesis, ideation, evaluation, routing, batch jobs, and customer-facing generation"
            ],
        ),
        "customer_impact": section(
            hints,
            ("customer_impact", "impact", "audience"),
            "LVC",
            "customer_success_owner",
            "Assess customer impact from vendor incident",
            evidence_ids,
            [
                "availability degradation, delayed generation, policy behavior change, or data security exposure"
            ],
            extra_keys=("audience", "impact", "tier", "region"),
        ),
        "message_owners": section(
            hints,
            ("message_owners", "owners", "spokespeople"),
            "LVO",
            "communications_owner",
            "Assign incident message owner",
            evidence_ids,
            ["incident commander, support lead, legal reviewer, customer communications owner"],
            name_keys=("name", "owner", "role", "team"),
            extra_keys=("role", "team", "channel"),
        ),
        "timelines": section(
            hints,
            ("timelines", "timeline", "updates"),
            "LVT",
            "incident_commander",
            "Maintain incident communication timeline",
            evidence_ids,
            [
                "initial assessment, first internal update, customer notice decision, follow-up cadence, closure note"
            ],
            extra_keys=("deadline", "cadence", "milestone"),
        ),
        "escalation_paths": section(
            hints,
            ("escalation_paths", "escalations", "escalation"),
            "LVE",
            "incident_commander",
            "Escalate LLM vendor incident communication",
            evidence_ids,
            _escalation_fallback(severity),
            extra_keys=("channel", "recipient", "threshold"),
        ),
        "customer_notification_steps": section(
            hints,
            ("customer_notification_steps", "customer_notifications", "notifications"),
            "LVN",
            "customer_success_owner",
            "Notify customers about LLM vendor incident",
            evidence_ids,
            _notification_fallback(severity),
            name_keys=("name", "audience", "channel", "recipient", "description"),
            extra_keys=("audience", "channel", "recipient", "deadline"),
        ),
        "closure_criteria": section(
            hints,
            ("closure_criteria", "closure", "exit_criteria"),
            "LVX",
            "incident_commander",
            "Close LLM vendor incident communications",
            evidence_ids,
            [
                "impact review completed, customer follow-up tracked, vendor RCA linked, "
                "and internal owners sign off on closure"
            ],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _highest_severity(incidents: list[dict[str, Any]]) -> str:
    rank = {"critical": 0, "sev1": 0, "high": 1, "sev2": 1, "medium": 2, "moderate": 2, "low": 3}
    severities = [compact(item.get("severity")).lower() or "medium" for item in incidents]
    return min(severities, key=lambda value: rank.get(value, 4), default="medium")


def _escalation_fallback(severity: str) -> list[str]:
    if severity in HIGH_SEVERITIES:
        return [
            "page incident commander, legal, security, support leadership, and executive sponsor"
        ]
    return ["route through incident commander and communications owner"]


def _notification_fallback(severity: str) -> list[str]:
    if severity in HIGH_SEVERITIES:
        return [
            "publish customer notification with impact, workaround, update cadence, and support contact"
        ]
    return ["prepare customer notice draft and send if impact is confirmed"]
