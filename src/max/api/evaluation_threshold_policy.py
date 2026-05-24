"""JSON API renderer for evaluation threshold policies."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.evaluation_threshold_policy.v1"
KIND = "max.api.evaluation_threshold_policy"


def evaluation_threshold_policy_to_json(payload: Mapping[str, Any]) -> str:
    """Render active evaluation threshold policies as deterministic API JSON."""
    policies = _policies(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(policies),
        "policies": policies,
        "invalid_policies": [row for row in policies if not row["thresholds_valid"]],
        "metadata": _metadata(payload, policies),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(policies: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "policy_count": len(policies),
        "valid_policy_count": sum(1 for row in policies if row["thresholds_valid"]),
        "invalid_policy_count": sum(1 for row in policies if not row["thresholds_valid"]),
    }


def _policies(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("policies")
    if not isinstance(source, list):
        source = payload.get("profile_policies")
    rows = [
        _policy_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["profile"]), str(row["dimension"])))


def _policy_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    approve = _float_or_zero(item.get("approve_threshold"))
    revise = _float_or_zero(item.get("revise_threshold"))
    reject = _float_or_zero(item.get("reject_threshold"))
    weights = _mapping(item.get("dimension_weights", item.get("weights")))
    return {
        "policy_id": item.get("policy_id") or item.get("id") or f"policy-{index}",
        "profile": str(item.get("profile") or "default"),
        "dimension": str(item.get("dimension") or "overall"),
        "dimension_weights": {str(key): _float_or_zero(value) for key, value in sorted(weights.items())},
        "normalized_weights": _normalized_weights(weights),
        "thresholds": {
            "approve": approve,
            "revise": revise,
            "reject": reject,
        },
        "thresholds_valid": reject <= revise <= approve,
        "recommendation_bands": {
            "approve": f">={approve}",
            "revise": f"{revise}..{approve}",
            "reject": f"<{revise}",
        },
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _normalized_weights(weights: Mapping[str, Any]) -> dict[str, float]:
    numeric = {str(key): max(_float_or_zero(value), 0.0) for key, value in weights.items()}
    total = sum(numeric.values())
    if not total:
        return {key: 0.0 for key in sorted(numeric)}
    return {key: round(value / total, 4) for key, value in sorted(numeric.items())}


def _metadata(payload: Mapping[str, Any], policies: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "policy_count": len(policies),
    }


def _mapping(value: Any, fallback: Any = None) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return fallback if isinstance(fallback, Mapping) else {}


def _float_or_zero(value: Any) -> float:
    try:
        return round(float(value or 0.0), 4)
    except (TypeError, ValueError):
        return 0.0
