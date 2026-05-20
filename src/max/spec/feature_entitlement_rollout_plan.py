"""Generate deterministic feature entitlement rollout plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-feature-entitlement-rollout-plan/v1"
KIND = "max.spec.feature_entitlement_rollout_plan"


def generate_feature_entitlement_rollout_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    matrix = _entitlement_matrix(spec)
    phases = _rollout_phases(spec)
    gaps = _readiness_gaps(matrix, phases)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "feature_count": len({row["feature"] for row in matrix}),
            "segment_count": len({row["segment"] for row in matrix}),
            "phase_count": len(phases),
            "readiness_gap_count": len(gaps),
        },
        "entitlement_matrix": matrix,
        "rollout_phases": phases,
        "readiness_gaps": gaps,
        "rollback_rules": _rollback_rules(spec),
    }


def render_feature_entitlement_rollout_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_feature_entitlement_rollout_plan(plan_or_spec)
    lines = ["# Feature Entitlement Rollout Plan", "", f"Schema version: {plan['schema_version']}", "", "## Entitlement Matrix", ""]
    for row in plan["entitlement_matrix"]:
        lines.append(f"- {row['id']}: {row['feature']} -> {row['segment']} rule={row['rule']} owner={row['owner']}")
    lines.extend(["", "## Rollout Phases", ""])
    for phase in plan["rollout_phases"]:
        lines.append(f"- {phase['id']}: {phase['name']} date={phase['date']} segments={', '.join(phase['segments'])} support={phase['support_owner']}")
    lines.extend(["", "## Readiness Gaps", ""])
    if plan["readiness_gaps"]:
        for gap in plan["readiness_gaps"]:
            lines.append(f"- {gap['id']}: {gap['gap']} owner={gap['owner']}")
    else:
        lines.append("- No readiness gaps identified.")
    lines.extend(["", "## Rollback Rules", ""])
    for rule in plan["rollback_rules"]:
        lines.append(f"- {rule['id']}: {rule['condition']} -> {rule['action']}")
    return "\n".join(lines).rstrip() + "\n"


def _entitlement_matrix(spec: dict[str, Any]) -> list[dict[str, str]]:
    features = _raw_items(spec, "features", "feature_entitlement_rollout")
    segments = _values(spec.get("customer_segments") or _dict(spec.get("metadata")).get("customer_segments"), ["all-customers"])
    rows = []
    if not features:
        features = [{"feature": "feature-intake"}]
    for feature_index, raw in enumerate(features, start=1):
        feature = _text(raw.get("feature") or raw.get("name")) or f"feature-{feature_index}"
        rules = _dict(raw.get("entitlement_rules") or raw.get("rules"))
        owner = _text(raw.get("owner")) or "entitlement_owner"
        feature_segments = _values(raw.get("segments") or raw.get("customer_segments"), segments)
        for segment in sorted(feature_segments, key=str.casefold):
            rule = _text(rules.get(segment) if rules else raw.get("rule")) or "entitlement-rule-required"
            rows.append({"id": "", "feature": feature, "segment": segment, "rule": rule, "owner": owner})
    rows = sorted(rows, key=lambda row: (row["feature"].casefold(), row["segment"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"FER-{index:03d}"
    return rows


def _rollout_phases(spec: dict[str, Any]) -> list[dict[str, Any]]:
    phases = _raw_items(spec, "rollout_phases", "feature_entitlement_rollout") or _raw_items(spec, "phases", "feature_entitlement_rollout")
    rows = []
    for index, raw in enumerate(phases, start=1):
        rows.append({"id": "", "name": _text(raw.get("name") or raw.get("phase")) or f"phase-{index}", "date": _text(raw.get("date") or raw.get("start_date")) or "date-required", "order": _int(raw.get("order"), index), "segments": _values(raw.get("segments"), ["all-customers"]), "support_owner": _text(raw.get("support_owner") or raw.get("support")) or "support-owner-required"})
    if not rows:
        rows.append({"id": "", "name": "pilot", "date": "date-required", "order": 1, "segments": ["all-customers"], "support_owner": "support-owner-required"})
    rows = sorted(rows, key=lambda row: (_date_key(row["date"]), row["order"], row["name"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"FRP-{index:03d}"
    return rows


def _readiness_gaps(matrix: list[dict[str, str]], phases: list[dict[str, Any]]) -> list[dict[str, str]]:
    gaps = []
    for row in matrix:
        if row["rule"] == "entitlement-rule-required":
            gaps.append({"id": "", "gap": f"missing entitlement rule for {row['feature']} / {row['segment']}", "owner": row["owner"]})
    for phase in phases:
        if phase["support_owner"] == "support-owner-required":
            gaps.append({"id": "", "gap": f"missing support owner for {phase['name']}", "owner": "support_owner"})
    for index, gap in enumerate(gaps, start=1):
        gap["id"] = f"FRG-{index:03d}"
    return gaps


def _rollback_rules(spec: dict[str, Any]) -> list[dict[str, str]]:
    rules = _raw_items(spec, "rollback_rules", "feature_entitlement_rollout") or _raw_items(spec, "rollback_conditions", "feature_entitlement_rollout")
    rows = []
    for index, raw in enumerate(rules, start=1):
        rows.append({"id": f"RBR-{index:03d}", "condition": _text(raw.get("condition") or raw.get("name")) or "rollback-condition-required", "action": _text(raw.get("action")) or "pause rollout and disable entitlement"})
    return rows or [{"id": "RBR-001", "condition": "rollback-condition-required", "action": "pause rollout and disable entitlement"}]


def _raw_items(spec: dict[str, Any], key: str, nested: str) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get(nested) or spec.get(nested))
    candidates = plan.get(key) or metadata.get(key) or spec.get(key)
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "entitlement_matrix" in value


def _date_key(value: str) -> tuple[int, str]:
    return (1, value.casefold()) if value == "date-required" else (0, value.casefold())


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
