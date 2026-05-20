"""Generate deterministic customer impact assessment plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.customer_impact_assessment_plan.v1"
KIND = "max.spec.customer_impact_assessment_plan"


def generate_customer_impact_assessment_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    segments = _segments(hints.get("segments") or hints.get("impacted_segments"), ctx)
    scenarios = _scenarios(hints.get("scenarios") or hints.get("impact_scenarios"), ctx, segments)
    visible = _truthy(hints.get("customer_visible")) or any("customer" in risk.casefold() for risk in ctx["risks"])
    severity = _severity(hints.get("severity"), scenarios, visible)
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, segment_count=len(segments), scenario_count=len(scenarios), customer_visible=visible, severity=severity),
        "impacted_segments": [_segment_record(index, segment, evidence_ids) for index, segment in enumerate(segments, start=1)],
        "impact_scenarios": [_scenario_record(index, scenario, evidence_ids) for index, scenario in enumerate(scenarios, start=1)],
        "severity_classification": {"severity": severity, "customer_visible": visible, "basis": "metadata override" if compact(hints.get("severity")) else "scenario and risk assessment"},
        "mitigations": _mitigations(hints, scenarios, evidence_ids),
        "communication_plan": _communications(hints, visible, evidence_ids),
        "validation_checks": _validation_checks(hints, segments, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _segment_record(index: int, segment: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"SEG{index}", "name": segment["name"], "owner": segment["owner"], "impact": segment["impact"], "evidence_reference_ids": evidence_ids}


def _scenario_record(index: int, scenario: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"IS{index}", "scenario": scenario["name"], "severity": scenario["severity"], "owner": scenario["owner"], "description": scenario["description"], "evidence_reference_ids": evidence_ids}


def _mitigations(hints: dict[str, Any], scenarios: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    owner = compact(hints.get("mitigation_owner")) or "customer_success_owner"
    records = _records(hints.get("mitigations"), "mitigation") or [
        {"name": f"Mitigate {scenario['name']}", "owner": scenario["owner"] or owner, "description": f"Reduce or remove customer impact for {scenario['name']}."}
        for scenario in scenarios
    ]
    return [{"id": f"MIT{index}", "action": row["name"], "owner": row["owner"] or owner, "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids} for index, row in enumerate(records, start=1)]


def _communications(hints: dict[str, Any], visible: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    records = _records(hints.get("communications") or hints.get("communication_plan"), "communication")
    if not records:
        records = [{"name": "customer notice" if visible else "internal customer-success brief", "owner": "customer_success_owner", "description": "Prepare customer-facing notice." if visible else "Brief customer-facing teams on impact assessment."}]
    return [{"id": f"COM{index}", "channel": row["name"], "owner": row["owner"] or "customer_success_owner", "message": row["description"] or row["name"], "evidence_reference_ids": evidence_ids} for index, row in enumerate(records, start=1)]


def _validation_checks(hints: dict[str, Any], segments: list[dict[str, str]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    records = _records(hints.get("validation_checks"), "validation") or [
        {"name": f"Validate impact for {segment['name']}", "owner": segment["owner"], "description": f"Confirm {segment['name']} can complete the primary workflow."}
        for segment in segments
    ]
    return [{"id": f"VC{index}", "check": row["name"], "owner": row["owner"] or "qa_owner", "description": row["description"] or row["name"], "evidence_reference_ids": evidence_ids} for index, row in enumerate(records, start=1)]


def _segments(value: Any, ctx: dict[str, Any]) -> list[dict[str, str]]:
    records = _records(value, "segment")
    if not records:
        records = [{"name": ctx["target_user"], "owner": "product_owner", "description": "Primary user segment."}]
    return sorted([{"name": row["name"], "owner": row["owner"] or "product_owner", "impact": row["description"] or "Assess workflow impact."} for row in records], key=lambda row: row["name"].casefold())


def _scenarios(value: Any, ctx: dict[str, Any], segments: list[dict[str, str]]) -> list[dict[str, str]]:
    records = _records(value, "scenario")
    if not records:
        records = [{"name": f"{ctx['workflow_context']} interruption", "owner": segments[0]["owner"], "description": "Primary workflow may be delayed or incomplete.", "severity": "medium"}]
    return sorted(
        [{"name": row["name"], "owner": row["owner"] or "product_owner", "description": row["description"] or row["name"], "severity": _severity(row.get("severity"), [], False)} for row in records],
        key=lambda row: (row["severity"], row["name"].casefold()),
    )


def _records(value: Any, default_name: str) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("segment") or item.get("scenario") or item.get("channel")) or f"{default_name} {index}", "owner": compact(item.get("owner")), "description": compact(item.get("impact") or item.get("description") or item.get("message")), "severity": compact(item.get("severity"))})
        else:
            name = compact(item) or f"{default_name} {index}"
            rows.append({"name": name, "owner": "", "description": "", "severity": ""})
    return rows


def _severity(value: Any, scenarios: list[dict[str, str]], visible: bool) -> str:
    text = compact(value).casefold()
    if text in {"critical", "high", "medium", "low"}:
        return text
    if any(item.get("severity") in {"critical", "high"} for item in scenarios):
        return "high"
    return "medium" if visible else "low"


def _truthy(value: Any) -> bool:
    return value is True or compact(value).casefold() in {"true", "yes", "1", "customer", "visible"}


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("customer_impact_assessment")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
