"""Generate deterministic prompt injection threat model plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.prompt_injection_threat_model_plan.v1"
KIND = "max.spec.prompt_injection_threat_model_plan"


def generate_prompt_injection_threat_model_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_injection_threat_model")
    entries = unique_records(
        named(
            hints.get("entry_points") or hints.get("inputs") or hints.get("channels"),
            ("entry_point", "channel", "surface"),
        ),
        [],
    )
    mitigations = unique_records(
        named(hints.get("mitigations") or hints.get("controls"), ("mitigation", "control")),
        [],
    )
    scenarios = unique_records(
        named(hints.get("attack_scenarios") or hints.get("scenarios") or hints.get("attacks"), ("scenario", "attack", "name")),
        [{"name": "indirect prompt injection", "severity": "high", "entry_point": "untrusted retrieved content"}],
    )
    blockers = _blockers(entries, mitigations, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            entry_point_count=len(entries),
            attack_scenario_count=len(scenarios),
            mitigation_count=len(mitigations),
            blocker_count=len(blockers),
        ),
        "entry_points": [
            item(
                "PTE",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Review prompt injection entry point",
                name_keys=("name", "entry_point", "channel", "surface"),
                extra_keys=("channel", "surface", "trust_level", "data_source"),
            )
            for index, record in enumerate(entries, start=1)
        ],
        "trust_boundaries": section(hints, ("trust_boundaries", "boundaries"), "PTB", "security_owner", "Review prompt trust boundary", evidence_ids, ["system prompt to user input, tool output to model context, retrieval corpus to answer generation"], extra_keys=("source", "destination", "trust_level")),
        "attack_scenarios": [
            item(
                "PTS",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Model prompt injection attack scenario",
                name_keys=("name", "scenario", "attack"),
                extra_keys=("entry_point", "target", "impact", "likelihood"),
            )
            for index, record in enumerate(scenarios, start=1)
        ],
        "mitigations": [
            item(
                "PTM",
                index,
                record,
                "model_owner",
                evidence_ids,
                "Operate prompt injection mitigation",
                name_keys=("name", "mitigation", "control"),
                extra_keys=("control", "coverage", "entry_point", "scenario"),
            )
            for index, record in enumerate(mitigations, start=1)
        ],
        "detection_checks": section(hints, ("detection_checks", "detections", "monitoring"), "PTD", "security_owner", "Detect prompt injection attempt", evidence_ids, ["jailbreak pattern alerts, tool-call anomaly detection, retrieval-source tagging, and refusal-rate monitoring"], extra_keys=("signal", "threshold", "cadence")),
        "residual_risks": section(hints, ("residual_risks", "risks"), "PTR", "risk_owner", "Track residual prompt injection risk", evidence_ids, ["untrusted content may still influence model behavior when controls are bypassed"], extra_keys=("impact", "likelihood", "accepted_by")),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(entries: list[dict[str, Any]], mitigations: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not entries:
        blockers.append(row("PTK", len(blockers) + 1, "missing prompt injection entry points", "security_owner", "Document user, retrieval, tool, file, and integration input surfaces before review.", evidence_ids, severity="high", status="blocked"))
    if not mitigations:
        blockers.append(row("PTK", len(blockers) + 1, "missing prompt injection mitigations", "model_owner", "Define isolation, instruction hierarchy, tool authorization, content filtering, and human escalation controls.", evidence_ids, severity="high", status="blocked"))
    for record in mitigations:
        if compact(record.get("status")).lower() in {"missing", "blocked", "unknown"}:
            blockers.append(row("PTK", len(blockers) + 1, compact(record.get("name")) or "incomplete mitigation", compact(record.get("owner")) or "model_owner", "Resolve incomplete prompt injection mitigation before launch.", evidence_ids, severity=compact(record.get("severity")) or "high", status=compact(record.get("status")) or "blocked"))
    return blockers
