"""Generate deterministic rollout decision log plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.rollout_decision_log_plan.v1"
KIND = "max.spec.rollout_decision_log_plan"


def generate_rollout_decision_log_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    decisions = _decisions(hints, ctx)
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, decision_count=len(decisions), pending_decision_count=sum(1 for item in decisions if item["status"] == "pending")),
        "decision_entries": [_decision(index, item, evidence_ids) for index, item in enumerate(decisions, start=1)],
        "decision_drivers": _drivers(hints, ctx, evidence_ids),
        "open_questions": _questions(hints, ctx, evidence_ids),
        "approvers": _approvers(hints, evidence_ids),
        "revisit_triggers": _triggers(hints, ctx, evidence_ids),
        "publication_notes": _publication(hints, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _decisions(hints: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, str]]:
    raw = hints.get("decisions") or hints.get("decision_entries")
    values = [raw] if isinstance(raw, dict) else raw if isinstance(raw, list) else string_list(raw)
    rows = []
    for index, item in enumerate(values, start=1):
        if isinstance(item, dict):
            rows.append({"decision": compact(item.get("decision") or item.get("name")) or f"decision {index}", "status": _status(item.get("status")), "rationale": compact(item.get("rationale") or item.get("reason")), "owner": compact(item.get("owner") or item.get("approver")) or "release_manager", "revisit_date": compact(item.get("revisit_date") or item.get("revisit")) or "next rollout review"})
        else:
            rows.append({"decision": compact(item) or f"decision {index}", "status": "pending", "rationale": "", "owner": "release_manager", "revisit_date": "next rollout review"})
    if not rows:
        recommendation = f" Recommendation context: {ctx['recommendation']}." if ctx["recommendation"] else ""
        rows.append({"decision": f"Rollout decision for {ctx['title']}", "status": "pending", "rationale": f"Decision pending based on launch readiness.{recommendation}", "owner": "release_manager", "revisit_date": "next rollout review"})
    return sorted(rows, key=lambda row: (row["status"] != "pending", row["decision"].casefold()))


def _decision(index: int, item: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"DE{index}", **item, "evidence_reference_ids": evidence_ids}


def _drivers(hints: dict[str, Any], ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    drivers = string_list(hints.get("drivers") or hints.get("decision_drivers")) or ctx["risks"] or ["readiness evidence"]
    return [{"id": f"DD{index}", "driver": driver, "evidence_reference_ids": evidence_ids} for index, driver in enumerate(sorted(drivers, key=str.casefold), start=1)]


def _questions(hints: dict[str, Any], ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    questions = string_list(hints.get("open_questions")) or [f"Is {ctx['title']} ready for the next rollout gate?"]
    return [{"id": f"OQ{index}", "question": question, "owner": "release_manager", "evidence_reference_ids": evidence_ids} for index, question in enumerate(questions, start=1)]


def _approvers(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    approvers = string_list(hints.get("approvers")) or ["product_owner", "engineering_owner", "release_manager"]
    return [{"id": f"AP{index}", "role": approver, "status": "pending", "evidence_reference_ids": evidence_ids} for index, approver in enumerate(sorted(approvers, key=str.casefold), start=1)]


def _triggers(hints: dict[str, Any], ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    triggers = string_list(hints.get("revisit_triggers")) or ctx["risks"] or ["new launch evidence changes rollout confidence"]
    return [{"id": f"RT{index}", "trigger": trigger, "evidence_reference_ids": evidence_ids} for index, trigger in enumerate(sorted(triggers, key=str.casefold), start=1)]


def _publication(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    channels = string_list(hints.get("publication_channels") or hints.get("publication_notes")) or ["release notes", "stakeholder update"]
    return [{"id": f"PN{index}", "channel": channel, "note": f"Publish rollout decision status to {channel}.", "evidence_reference_ids": evidence_ids} for index, channel in enumerate(sorted(channels, key=str.casefold), start=1)]


def _status(value: Any) -> str:
    text = compact(value).casefold()
    return text if text in {"approved", "rejected", "deferred", "pending"} else "pending"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("rollout_decision_log")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
