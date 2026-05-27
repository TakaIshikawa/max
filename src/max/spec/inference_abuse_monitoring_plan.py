"""Generate deterministic inference abuse monitoring plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.inference_abuse_monitoring_plan.v1"
KIND = "max.spec.inference_abuse_monitoring_plan"


def generate_inference_abuse_monitoring_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "inference_abuse_monitoring")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    signals = unique_records(
        named(hints.get("abuse_signals") or hints.get("signals"), ("signal", "metric", "name")),
        [{"name": "prompt abuse spike", "threshold": "3x baseline", "owner": "trust_safety_owner"}],
    )
    signal_rows = [_signal("IAM", index, record, evidence_ids) for index, record in enumerate(signals, start=1)]
    blockers = _blockers(signal_rows, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Inference Abuse Monitoring Plan",
        "summary": source_summary(ctx, abuse_signal_count=len(signal_rows), blocker_count=len(blockers)),
        "abuse_signals": signal_rows,
        "detection_thresholds": section(
            hints,
            ("detection_thresholds", "thresholds"),
            "IAT",
            "trust_safety_owner",
            "Set abuse detection threshold",
            evidence_ids,
            [{"name": row["name"], "threshold": row.get("threshold"), "owner": row["owner"]} for row in signal_rows],
            extra_keys=("threshold", "window", "metric"),
        ),
        "alert_routing": section(hints, ("alert_routing", "routing", "alert_owners"), "IAA", "trust_safety_owner", "Route abuse alert", evidence_ids, ["trust and safety on-call, security incident channel, and model operations owner"]),
        "investigation_steps": section(hints, ("investigation_steps", "triage_steps", "triage"), "IAI", "trust_safety_owner", "Investigate inference abuse signal", evidence_ids, ["correlate request patterns, inspect policy labels, review tenant history, and preserve evidence"]),
        "escalation_owners": section(hints, ("escalation_owners", "owners", "escalations"), "IAE", "trust_safety_owner", "Escalate inference abuse finding", evidence_ids, ["trust safety lead, security owner, legal contact, and product owner"]),
        "suppression_rules": section(hints, ("suppression_rules", "suppressions"), "IAS", "trust_safety_owner", "Apply abuse alert suppression rule", evidence_ids, ["time-boxed suppression requires owner, reason, expiry, and validation sample"]),
        "evidence_requirements": section(hints, ("evidence_requirements", "evidence"), "IAV", "trust_safety_owner", "Capture abuse monitoring evidence", evidence_ids, ["signal snapshot, sampled requests, decision log, and escalation outcome"]),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _signal(prefix: str, index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    data = item(prefix, index, record, "trust_safety_owner", evidence_ids, "Monitor inference abuse signal", name_keys=("name", "signal", "metric"), extra_keys=("threshold", "window", "metric", "evidence_id"))
    if isinstance(record.get("metadata"), dict):
        data["metadata"] = dict(sorted(record["metadata"].items()))
    return data


def _blockers(signal_rows: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for signal in signal_rows:
        if not compact(signal.get("threshold")):
            blockers.append(row("IAB", len(blockers) + 1, f"missing threshold for {signal['name']}", signal["owner"], "Abuse signal must define a detection threshold before monitoring is actionable.", evidence_ids, severity="high", signal=signal["name"]))
        if signal["owner"] in {"", "trust_safety_owner"} and not compact(signal.get("owner_override")):
            blockers.append(row("IAB", len(blockers) + 1, f"missing alert owner for {signal['name']}", "trust_safety_owner", "Abuse signal must identify an accountable alert owner.", evidence_ids, severity="high", signal=signal["name"]))
    return blockers
