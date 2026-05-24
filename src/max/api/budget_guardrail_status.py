"""JSON API renderer for budget guardrail status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, mapping, rounded, source_metadata


SCHEMA_VERSION = "max.api.budget_guardrail_status.v1"
KIND = "max.api.budget_guardrail_status"


def budget_guardrail_status_to_json(payload: Mapping[str, Any]) -> str:
    dimensions = _dimensions(payload)
    guardrails = _guardrails(payload, dimensions)
    breaches = _breaches(payload, dimensions, guardrails)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "budget_summary": _budget_summary(payload, dimensions, breaches),
        "dimensions": dimensions,
        "guardrails": guardrails,
        "breaches": breaches,
        "reservations": _reservations(payload),
        "next_actions": _next_actions(payload, breaches),
        "metadata": source_metadata(payload, dimension_count=len(dimensions)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _dimensions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("dimensions")
    if not isinstance(source, list):
        source = payload.get("budgets")
    rows = [
        _dimension(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: str(row["dimension"]))


def _dimension(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    limit = float_or_zero(item.get("limit", item.get("budget")))
    spent = float_or_zero(item.get("spent", item.get("spend_to_date")))
    reserved = float_or_zero(item.get("reserved", item.get("reserved_budget")))
    remaining = item.get("remaining")
    if remaining is None:
        remaining = limit - spent - reserved
    utilization = item.get("utilization_percent")
    if utilization is None:
        utilization = (spent + reserved) / limit * 100 if limit else 0
    return {
        "dimension": item.get("dimension") or item.get("type") or f"budget-{index}",
        "unit": item.get("unit") or item.get("currency"),
        "limit": rounded(limit),
        "spent": rounded(spent),
        "reserved": rounded(reserved),
        "remaining": rounded(remaining),
        "utilization_percent": rounded(utilization),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _guardrails(payload: Mapping[str, Any], dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("guardrails"))
    if explicit:
        return sorted(
            [
                {
                    "dimension": item.get("dimension") or item.get("type") or "unknown",
                    "soft_limit_percent": rounded(item.get("soft_limit_percent", item.get("soft_threshold_percent", 80))),
                    "hard_limit_percent": rounded(item.get("hard_limit_percent", item.get("hard_threshold_percent", 100))),
                }
                for item in explicit
            ],
            key=lambda row: str(row["dimension"]),
        )
    return [
        {"dimension": row["dimension"], "soft_limit_percent": 80.0, "hard_limit_percent": 100.0}
        for row in dimensions
    ]


def _breaches(
    payload: Mapping[str, Any],
    dimensions: list[dict[str, Any]],
    guardrails: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("breaches"))
    if explicit:
        return sorted(
            [{"dimension": item.get("dimension") or item.get("type") or "unknown", "level": item.get("level") or item.get("severity"), "utilization_percent": rounded(item.get("utilization_percent")), "message": item.get("message")} for item in explicit],
            key=lambda row: (str(row["dimension"]), str(row["level"])),
        )
    thresholds = {str(row["dimension"]): row for row in guardrails}
    rows = []
    for dimension in dimensions:
        guardrail = thresholds.get(str(dimension["dimension"]), {})
        utilization = float_or_zero(dimension["utilization_percent"])
        level = None
        if utilization >= float_or_zero(guardrail.get("hard_limit_percent")):
            level = "hard"
        elif utilization >= float_or_zero(guardrail.get("soft_limit_percent")):
            level = "soft"
        if level:
            rows.append(
                {
                    "dimension": dimension["dimension"],
                    "level": level,
                    "utilization_percent": rounded(utilization),
                    "message": f"{level} budget guardrail breached",
                }
            )
    return sorted(rows, key=lambda row: (str(row["dimension"]), str(row["level"])))


def _budget_summary(
    payload: Mapping[str, Any],
    dimensions: list[dict[str, Any]],
    breaches: list[dict[str, Any]],
) -> dict[str, Any]:
    source = mapping(payload.get("budget_summary")) or mapping(payload.get("summary"))
    return {
        "total_limit": rounded(source.get("total_limit", sum(float_or_zero(row["limit"]) for row in dimensions))),
        "total_spent": rounded(source.get("total_spent", sum(float_or_zero(row["spent"]) for row in dimensions))),
        "total_reserved": rounded(source.get("total_reserved", sum(float_or_zero(row["reserved"]) for row in dimensions))),
        "total_remaining": rounded(source.get("total_remaining", sum(float_or_zero(row["remaining"]) for row in dimensions))),
        "soft_breach_count": int(source.get("soft_breach_count", sum(1 for row in breaches if row["level"] == "soft"))),
        "hard_breach_count": int(source.get("hard_breach_count", sum(1 for row in breaches if row["level"] == "hard"))),
    }


def _reservations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [{"id": item.get("id") or f"R{index}", "dimension": item.get("dimension") or item.get("type"), "amount": rounded(item.get("amount")), "owner": item.get("owner")} for index, item in enumerate(list_of_maps(payload.get("reservations")), start=1)],
        key=lambda row: str(row["id"]),
    )


def _next_actions(payload: Mapping[str, Any], breaches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("next_actions"))
    if explicit:
        return sorted([{"id": item.get("id") or f"A{index}", "action": item.get("action") or item.get("title"), "dimension": item.get("dimension"), "owner": item.get("owner")} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["id"]))
    return sorted(
        [{"id": f"review-{row['dimension']}", "action": "Review budget guardrail breach", "dimension": row["dimension"], "owner": None} for row in breaches],
        key=lambda row: str(row["id"]),
    )
