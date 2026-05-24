"""Generate deterministic human review escalation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.human_review_escalation_plan.v1"
KIND = "max.spec.human_review_escalation_plan"
RISK_LEVELS = {"critical", "high", "medium", "moderate", "low"}


def generate_human_review_escalation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "human_review_escalation")
    triggers = [
        _trigger(index, record, evidence_ids)
        for index, record in enumerate(
            unique_records(
                _trigger_candidates(
                    hints.get("escalation_triggers")
                    or hints.get("triggers")
                    or hints.get("risks")
                    or hints.get("conditions"),
                ),
                [{"name": "ambiguous or high-risk generated idea", "severity": "high"}],
            ),
            start=1,
        )
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, trigger_count=len(triggers)),
        "escalation_triggers": triggers,
        "reviewer_queue": _named_section(
            hints,
            ("reviewer_queue", "queue", "reviewers"),
            ("queue", "team", "channel"),
            "HRQ",
            "review_owner",
            "Route item to reviewer queue",
            evidence_ids,
            ["human review queue"],
            name_keys=("name", "queue", "team", "channel", "description"),
            extra_keys=("queue", "team", "channel"),
        ),
        "sla": _named_section(
            hints,
            ("sla", "service_level", "review_sla"),
            ("target", "sla", "deadline"),
            "HRS",
            "review_owner",
            "Define human review SLA",
            evidence_ids,
            ["review-required"],
            name_keys=("name", "target", "sla", "deadline", "description"),
            extra_keys=("sla", "target", "deadline"),
        ),
        "decision_outcomes": section(
            hints,
            ("decision_outcomes", "outcomes", "decisions"),
            "HRD",
            "review_owner",
            "Record human review decision outcome",
            evidence_ids,
            ["approve, reject, revise, or escalate"],
        ),
        "override_logging": section(
            hints,
            ("override_logging", "overrides", "override_log"),
            "HRO",
            "risk_owner",
            "Log human review override",
            evidence_ids,
            ["capture override reason, approver, timestamp, and affected generated idea"],
        ),
        "notification_path": _named_section(
            hints,
            ("notification_path", "notifications", "notification"),
            ("channel", "recipient", "queue"),
            "HRN",
            "program_owner",
            "Notify human review stakeholders",
            evidence_ids,
            ["notify requester, reviewer queue, risk owner, and affected workflow owner"],
            name_keys=("name", "channel", "recipient", "queue", "description"),
            extra_keys=("channel", "recipient", "queue"),
        ),
        "evidence_references": ctx["evidence_references"],
    }


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


def _trigger_candidates(value: Any) -> Any:
    candidates = named(value, ("trigger", "condition", "risk", "scenario"))
    if not isinstance(candidates, list):
        return candidates
    return [
        {
            **record,
            "severity": _risk(record.get("risk_level") or record.get("risk") or record.get("severity")),
        }
        if isinstance(record, dict)
        else record
        for record in candidates
    ]


def _trigger(index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    risk_level = _risk(record.get("risk_level") or record.get("risk") or record.get("severity"))
    name = (
        compact(record.get("trigger"))
        or compact(record.get("condition"))
        or compact(record.get("scenario"))
        or compact(record.get("name"))
        or "ambiguous or high-risk generated idea"
    )
    return item(
        "HRT",
        index,
        {**record, "name": name, "risk_level": risk_level, "severity": risk_level},
        "review_owner",
        evidence_ids,
        "Escalate generated idea to human review",
        extra_keys=("trigger", "condition", "scenario", "risk_level", "queue"),
    )


def _risk(value: Any) -> str:
    text = compact(value).lower()
    return text if text in RISK_LEVELS else "high"
