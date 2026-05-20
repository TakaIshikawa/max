"""Deterministic feature flag rollout plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.feature_flag_rollout_plan"
SCHEMA_VERSION = "max.design_brief.feature_flag_rollout_plan.v1"


def generate_design_brief_feature_flag_rollout_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "feature_flag_rollout_plan")
    flags = _flags(data)
    stages = _stages(data, flags)
    risks = _risks(flags)
    status = "blocked" if any(risk["severity"] == "high" for risk in risks) else ("needs_attention" if risks else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"recommendation_status": status, "flag_count": len(flags), "launch_risk_count": len(risks)},
        "feature_flags": flags,
        "rollout_stages": stages,
        "launch_risks": risks,
    }


def _flags(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("flags") or data.get("feature_flags")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("FF", index)),
                "flag": first_text(item.get("flag"), item.get("name"), default=f"feature flag {index}"),
                "owner": text(item.get("owner")),
                "target_segments": evidence(item.get("target_segments") or item.get("segments")),
                "kill_switch": text(item.get("kill_switch")),
                "guardrail_metrics": evidence(item.get("guardrail_metrics") or item.get("metrics")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "flag")


def _stages(data: Mapping[str, Any], flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stage_rows = list_of_dicts(data.get("rollout_stages") or data.get("stages"))
    if not stage_rows:
        stage_rows = [{"stage": "internal", "percent": 5}, {"stage": "beta", "percent": 25}, {"stage": "general availability", "percent": 100}]
    rows = []
    for flag in flags:
        for index, item in enumerate(stage_rows, start=1):
            rows.append(
                {
                    "id": f"{flag['id']}-S{index}",
                    "flag": flag["flag"],
                    "stage": first_text(item.get("stage"), item.get("name"), default=f"stage {index}"),
                    "target_segment": text(item.get("target_segment") or item.get("segment")),
                    "percent": item.get("percent", item.get("percentage", "")),
                    "owner": text(item.get("owner"), flag["owner"]),
                    "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
                }
            )
    return sorted_rows(rows, "flag", "stage")


def _risks(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not flags:
        return [gap("missing_feature_flags", "No feature flags were provided.")]
    risks = []
    for flag in flags:
        key = flag["flag"].lower().replace(" ", "_")
        if not flag["kill_switch"]:
            risks.append(gap(f"{key}_missing_kill_switch", f"{flag['flag']} is missing a kill switch."))
        if not flag["guardrail_metrics"]:
            risks.append(gap(f"{key}_missing_guardrail_metrics", f"{flag['flag']} is missing guardrail metrics.", "medium"))
        if not flag["owner"]:
            risks.append(gap(f"{key}_missing_owner", f"{flag['flag']} is missing an owner."))
    return risks
