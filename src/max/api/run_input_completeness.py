"""JSON API renderer for pipeline run input completeness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.run_input_completeness.v1"
KIND = "max.api.run_input_completeness"
STAGE_ORDER = ("fetch", "synthesize", "ideate", "evaluate", "spec_generation", "publication")


def run_input_completeness_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    required = _mapping(payload.get("required_inputs", payload.get("required")))
    observed = _mapping(payload.get("observed_inputs", payload.get("observed")))
    optional = _mapping(payload.get("optional_inputs", payload.get("optional")))
    reasons = _reason_mapping(payload.get("missing_reasons", payload.get("reasons")))
    stages = [_stage(stage, required.get(stage, []), observed.get(stage, []), optional.get(stage, []), reasons) for stage in _stage_order(required, observed, optional)]
    blocked = [row["stage"] for row in stages if row["blocked"]]
    warnings = [warning for row in stages for warning in row["warnings"]]
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"ready": not blocked, "stage_count": len(stages), "blocked_stage_count": len(blocked), "warning_count": len(warnings)},
        "stages": stages,
        "blocked_stages": blocked,
        "warnings": warnings,
        "recommended_remediation_actions": _actions(stages),
        "metadata": _metadata(payload, stages, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _stage(stage: str, required: list[str], observed: list[str], optional: list[str], reasons: dict[tuple[str, str], str]) -> dict[str, Any]:
    observed_set = set(observed)
    missing = sorted(set(required) - observed_set)
    optional_missing = sorted(set(optional) - observed_set)
    warnings = [{"stage": stage, "input": item, "reason": reasons.get((stage, item), "")} for item in optional_missing]
    return {"stage": stage, "required_inputs": sorted(required), "observed_inputs": sorted(observed), "optional_inputs": sorted(optional), "missing_required_inputs": [{"input": item, "reason": reasons.get((stage, item), "")} for item in missing], "missing_optional_inputs": optional_missing, "complete": not missing, "blocked": bool(missing), "warnings": warnings}


def _actions(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in stages:
        for missing in row["missing_required_inputs"]:
            rows.append({"stage": row["stage"], "input": missing["input"], "action": f"Provide required input {missing['input']}"})
    return rows


def _stage_order(*mappings: dict[str, list[str]]) -> list[str]:
    seen = set().union(*(mapping.keys() for mapping in mappings))
    ordered = [stage for stage in STAGE_ORDER if stage in seen]
    ordered.extend(sorted(seen - set(ordered)))
    return ordered


def _mapping(value: Any) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    if isinstance(value, Mapping):
        for stage, inputs in value.items():
            stage_key = _bucket(stage, "unknown-stage")
            if isinstance(inputs, list):
                rows[stage_key] = sorted({_text(item) for item in inputs if _text(item)})
    return rows


def _reason_mapping(value: Any) -> dict[tuple[str, str], str]:
    rows: dict[tuple[str, str], str] = {}
    if isinstance(value, Mapping):
        for key, reason in value.items():
            if isinstance(key, str) and "." in key:
                stage, input_name = key.split(".", 1)
                rows[(_bucket(stage, "unknown-stage"), _text(input_name))] = _text(reason)
    return rows


def _metadata(payload: Mapping[str, Any], stages: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "stage_count": len(stages)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
