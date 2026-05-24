"""Generate deterministic customer consent replay exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.customer_consent_replay_exception_plan.v1"
KIND = "max.spec.customer_consent_replay_exception_plan"


def generate_customer_consent_replay_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_consent_replay_exception")
    replay_events = unique_records(
        named(
            hints.get("replay_events") or hints.get("consent_events") or hints.get("events"),
            ("event", "customer_segment", "consent_version"),
        ),
        [{"name": "customer consent replay event", "owner": "privacy_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, replay_event_count=len(replay_events)),
        "replay_events": [
            item(
                "CCR",
                index,
                record,
                "privacy_owner",
                evidence_ids,
                "Review replayed customer consent event",
                name_keys=("name", "event", "customer_segment", "consent_version"),
                extra_keys=("event", "customer_segment", "occurred_at", "consent_version", "request_id"),
            )
            for index, record in enumerate(replay_events, start=1)
        ],
        "affected_segments": section(
            hints,
            ("affected_segments", "segments", "customers", "customer_segments"),
            "CCS",
            "support_owner",
            "Confirm affected consent replay segment",
            evidence_ids,
            ["affected customer segment, tenant cohort, or consent population"],
            extra_keys=("customer_segment", "tenant", "region"),
        ),
        "exception_reason": section(
            hints,
            ("exception_reason", "reason", "rationale", "justification"),
            "CCJ",
            "privacy_owner",
            "Document consent replay exception reason",
            evidence_ids,
            ["why normal consent processing cannot correct the event stream"],
        ),
        "validation_checks": section(
            hints,
            ("validation_checks", "validation", "checks"),
            "CCV",
            "data_owner",
            "Validate consent replay result",
            evidence_ids,
            ["pre/post consent state comparison, duplicate replay guard, and segment sample validation"],
        ),
        "notification_plan": section(
            hints,
            ("notification_plan", "notifications", "customer_notification"),
            "CCN",
            "support_owner",
            "Notify affected customers",
            evidence_ids,
            ["customer notification criteria, support messaging, and exception owner checkpoint"],
        ),
        "audit_evidence": section(
            hints,
            ("audit_evidence", "evidence", "artifacts"),
            "CCE",
            "privacy_owner",
            "Capture consent replay audit evidence",
            evidence_ids,
            ["replay request, event IDs, before/after consent state, validation output, and approvals"],
        ),
        "expiry_workflow": section(
            hints,
            ("expiry_workflow", "expiry", "expiration"),
            "CCX",
            "privacy_owner",
            "Expire consent replay exception",
            evidence_ids,
            ["close exception after replay validation and customer communication"],
        ),
        "rollback_plan": section(
            hints,
            ("rollback_plan", "rollback", "backout"),
            "CCB",
            "data_owner",
            "Rollback consent replay",
            evidence_ids,
            ["restore prior consent state and pause downstream consent propagation on failed validation"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
