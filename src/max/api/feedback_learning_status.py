"""JSON API renderer for feedback learning status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, rounded, source_metadata, strings


SCHEMA_VERSION = "max.api.feedback_learning_status.v1"
KIND = "max.api.feedback_learning_status"
APPROVAL_OUTCOMES = {"accepted", "approved", "positive"}
REJECTION_OUTCOMES = {"rejected", "declined", "negative"}


def feedback_learning_status_to_json(payload: Mapping[str, Any]) -> str:
    outcomes = _outcomes(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, outcomes),
        "outcomes": outcomes,
        "weight_adjustments": _weight_adjustments(payload),
        "affected_profiles": _affected_profiles(payload, outcomes),
        "anomalies": _anomalies(payload),
        "learning_window": _learning_window(payload),
        "next_actions": _next_actions(payload),
        "metadata": source_metadata(payload, outcome_count=len(outcomes)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _outcomes(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("outcomes")
    if not isinstance(source, list):
        source = payload.get("feedback_outcomes")
    rows = [
        {
            "feedback_id": item.get("feedback_id") or item.get("id") or f"F{index}",
            "outcome": str(item.get("outcome") or item.get("status") or "neutral").lower(),
            "profile": item.get("profile") or item.get("profile_id"),
            "dimension": item.get("dimension"),
            "confidence_delta": rounded(item.get("confidence_delta", item.get("delta"))),
            "created_at": item.get("created_at"),
            "metadata": dict(mapping(item.get("metadata"))),
        }
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["feedback_id"]), str(row["profile"] or ""), str(row["outcome"])))


def _summary(payload: Mapping[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, int]:
    source = mapping(payload.get("summary"))
    counts = Counter(str(row["outcome"]) for row in outcomes)
    approvals = sum(counts[outcome] for outcome in APPROVAL_OUTCOMES)
    rejections = sum(counts[outcome] for outcome in REJECTION_OUTCOMES)
    return {
        "approval_count": int_or_zero(source.get("approval_count", approvals)),
        "rejection_count": int_or_zero(source.get("rejection_count", rejections)),
        "neutral_count": int_or_zero(source.get("neutral_count", len(outcomes) - approvals - rejections)),
        "total_count": int_or_zero(source.get("total_count", len(outcomes))),
    }


def _weight_adjustments(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "dimension": item.get("dimension") or item.get("name") or f"dimension-{index}",
                "previous_weight": rounded(item.get("previous_weight")),
                "current_weight": rounded(item.get("current_weight")),
                "delta": rounded(item.get("delta", float_or_zero(item.get("current_weight")) - float_or_zero(item.get("previous_weight")))),
                "reason": item.get("reason"),
            }
            for index, item in enumerate(list_of_maps(payload.get("weight_adjustments")), start=1)
        ],
        key=lambda row: str(row["dimension"]),
    )


def _affected_profiles(payload: Mapping[str, Any], outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = list_of_maps(payload.get("affected_profiles"))
    if explicit:
        return sorted(
            [{"profile": item.get("profile") or item.get("profile_id") or item.get("name"), "feedback_ids": sorted(str(value) for value in strings(item.get("feedback_ids"))), "outcome_count": int_or_zero(item.get("outcome_count"))} for item in explicit],
            key=lambda row: str(row["profile"] or ""),
        )
    grouped: dict[str, list[str]] = {}
    for outcome in outcomes:
        if outcome["profile"]:
            grouped.setdefault(str(outcome["profile"]), []).append(str(outcome["feedback_id"]))
    return [{"profile": profile, "feedback_ids": sorted(ids), "outcome_count": len(ids)} for profile, ids in sorted(grouped.items())]


def _anomalies(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [{"id": item.get("id") or f"N{index}", "type": item.get("type"), "message": item.get("message") or item.get("reason"), "severity": item.get("severity")} for index, item in enumerate(list_of_maps(payload.get("anomalies")), start=1)],
        key=lambda row: str(row["id"]),
    )


def _learning_window(payload: Mapping[str, Any]) -> dict[str, Any]:
    source = mapping(payload.get("learning_window")) or mapping(payload.get("window"))
    return {
        "started_at": source.get("started_at") or source.get("start"),
        "ended_at": source.get("ended_at") or source.get("end"),
        "feedback_count": int_or_zero(source.get("feedback_count")),
    }


def _next_actions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [{"id": item.get("id") or f"A{index}", "action": item.get("action") or item.get("title"), "owner": item.get("owner")} for index, item in enumerate(list_of_maps(payload.get("next_actions")), start=1)],
        key=lambda row: str(row["id"]),
    )
