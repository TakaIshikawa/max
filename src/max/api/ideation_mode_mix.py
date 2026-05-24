"""JSON API renderer for ideation mode mix reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.ideation_mode_mix.v1"
KIND = "max.api.ideation_mode_mix"


def ideation_mode_mix_to_json(payload: Mapping[str, Any]) -> str:
    """Render ideation mode mix data as deterministic API JSON."""
    modes = _modes(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, modes),
        "mode_totals": modes,
        "metadata": _metadata(payload, modes),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(payload: Mapping[str, Any], modes: list[dict[str, Any]]) -> dict[str, Any]:
    generated = sum(row["generated_count"] for row in modes)
    evaluated = sum(row["evaluated_count"] for row in modes)
    approved = sum(row["approved_count"] for row in modes)
    best = max(modes, key=lambda row: (row["approval_rate"], row["average_score"], row["mode"]), default=None)
    return {
        "total_generated": generated,
        "total_evaluated": evaluated,
        "total_approved": approved,
        "evaluation_rate": _rate(evaluated, generated),
        "approval_rate": _rate(approved, evaluated),
        "best_performing_mode": best["mode"] if best else None,
    }


def _modes(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("ideation_records")
    if not isinstance(source, list):
        source = payload.get("modes")
    rows = [
        _mode_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: str(row["mode"]))


def _mode_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    generated = _int_or_zero(item.get("generated_count", item.get("generated")))
    evaluated = _int_or_zero(item.get("evaluated_count", item.get("evaluated")))
    approved = _int_or_zero(item.get("approved_count", item.get("approved")))
    return {
        "mode": str(item.get("mode") or f"mode-{index}"),
        "generated_count": generated,
        "evaluated_count": evaluated,
        "approved_count": approved,
        "average_score": _float_or_zero(item.get("average_score")),
        "evaluation_rate": _rate(evaluated, generated),
        "approval_rate": _rate(approved, evaluated),
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _metadata(payload: Mapping[str, Any], modes: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "mode_count": len(modes),
    }


def _rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_or_zero(value: Any) -> float:
    try:
        return round(float(value or 0.0), 4)
    except (TypeError, ValueError):
        return 0.0
