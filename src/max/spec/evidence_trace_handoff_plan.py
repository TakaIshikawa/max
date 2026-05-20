"""Generate deterministic evidence trace handoff plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.evidence_trace_handoff_plan.v1"
KIND = "max.spec.evidence_trace_handoff_plan"


def generate_evidence_trace_handoff_plan(spec_like: Any) -> dict[str, Any]:
    """Return a handoff plan for evidence chains and implementation review."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "evidence_trace_handoff")
    chain = {
        "signals": _values(hints.get("signals") or _evidence_values(spec, "signal_ids")),
        "insights": _values(hints.get("insights") or _evidence_values(spec, "insight_ids")),
        "units": _values(hints.get("units") or spec.get("units")),
        "evaluations": _values(hints.get("evaluations") or spec.get("evaluations")),
        "specs": _values(hints.get("specs") or spec.get("specs")),
    }
    evidence_ids = _evidence_ids(ctx)
    trace_gaps = _trace_gaps(chain)
    assumptions = _assumptions(hints.get("assumptions") or spec.get("assumptions") or ctx["risks"])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, evidence_reference_count=len(evidence_ids), trace_gap_count=len(trace_gaps), assumption_count=len(assumptions)),
        "evidence_bundle": _bundle(chain, evidence_ids),
        "trace_gaps": trace_gaps,
        "assumptions": assumptions,
        "validation_checkpoints": _validation_checkpoints(chain, evidence_ids),
        "handoff_actions": _handoff_actions(trace_gaps, assumptions, evidence_ids),
        "review_owners": _review_owners(hints.get("owners") or spec.get("owners")),
        "evidence_references": ctx["evidence_references"],
    }


def _bundle(chain: dict[str, list[str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    bundle: list[dict[str, Any]] = []
    for key in ("signals", "insights", "units", "evaluations", "specs"):
        for index, value in enumerate(chain[key], start=1):
            bundle.append({"id": f"{key[:3].upper()}{index}", "type": key[:-1], "reference": value, "evidence_reference_ids": evidence_ids})
    return bundle


def _trace_gaps(chain: dict[str, list[str]]) -> list[dict[str, Any]]:
    labels = {
        "signals": "source signal",
        "insights": "derived insight",
        "units": "implementation unit",
        "evaluations": "evaluation result",
        "specs": "target spec",
    }
    gaps: list[dict[str, Any]] = []
    for key, label in labels.items():
        if not chain[key]:
            gaps.append({"id": f"GAP{len(gaps) + 1}", "type": key, "severity": "high", "description": f"Missing {label} references for handoff traceability."})
    return gaps


def _assumptions(value: Any) -> list[dict[str, Any]]:
    assumptions = _values(value)
    return [
        {"id": f"ASM{index}", "assumption": assumption, "owner": "implementation_owner", "status": "unresolved"}
        for index, assumption in enumerate(assumptions, start=1)
    ]


def _validation_checkpoints(chain: dict[str, list[str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    checkpoints = [
        ("CP1", "trace_completeness", "Confirm each implementation unit maps to a signal, insight, evaluation, and target spec."),
        ("CP2", "assumption_review", "Review unresolved assumptions before implementation starts."),
        ("CP3", "evidence_access", "Confirm implementation and review owners can access every referenced evidence artifact."),
    ]
    return [
        {
            "id": item_id,
            "type": item_type,
            "description": description,
            "owner": "implementation_owner",
            "complete": all(chain.values()) if item_type == "trace_completeness" else False,
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, item_type, description in checkpoints
    ]


def _handoff_actions(trace_gaps: list[dict[str, Any]], assumptions: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    actions = [
        {
            "id": "HA1",
            "type": "handoff_packet",
            "owner": "implementation_owner",
            "action": "Package evidence bundle, open assumptions, validation checkpoints, and review owners for implementation handoff.",
            "evidence_reference_ids": evidence_ids,
        }
    ]
    if trace_gaps:
        actions.append({"id": "HA2", "type": "close_trace_gaps", "owner": "research_owner", "action": "Close trace gaps or explicitly waive them before build.", "evidence_reference_ids": evidence_ids})
    if assumptions:
        actions.append({"id": "HA3", "type": "resolve_assumptions", "owner": "product_owner", "action": "Resolve or accept unresolved assumptions before implementation signoff.", "evidence_reference_ids": evidence_ids})
    return actions


def _review_owners(value: Any) -> list[dict[str, str]]:
    owners = value if isinstance(value, dict) else {}
    return [
        {"role": "implementation_owner", "owner": compact(owners.get("implementation_owner")) or "implementation_owner"},
        {"role": "research_owner", "owner": compact(owners.get("research_owner")) or "research_owner"},
        {"role": "product_owner", "owner": compact(owners.get("product_owner")) or "product_owner"},
    ]


def _evidence_values(spec: dict[str, Any], key: str) -> list[str]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    return string_list(evidence.get(key))


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _values(value: Any) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold)


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
