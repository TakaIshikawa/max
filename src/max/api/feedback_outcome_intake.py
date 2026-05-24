"""JSON API renderer for feedback outcome intake."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.feedback_outcome_intake.v1"
KIND = "max.api.feedback_outcome_intake"
OUTCOME_ALIASES = {
    "approve": "approved",
    "approved": "approved",
    "accepted": "approved",
    "reject": "rejected",
    "rejected": "rejected",
    "declined": "rejected",
    "defer": "deferred",
    "deferred": "deferred",
    "complete": "completed",
    "completed": "completed",
    "done": "completed",
    "fail": "failed",
    "failed": "failed",
}


def feedback_outcome_intake_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    accepted, invalid = _records(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(accepted, invalid),
        "accepted_outcomes": accepted,
        "invalid_records": invalid,
        "profile_totals": _profile_totals(accepted),
        "reviewer_queues": _reviewer_queues(accepted),
        "weight_update_candidates": _weight_candidates(accepted),
        "metadata": _metadata(payload, accepted, invalid, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _records(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = payload.get("feedback") if isinstance(payload.get("feedback"), list) else payload.get("outcomes")
    if not isinstance(source, list):
        source = payload.get("feedback_records")
    accepted = []
    invalid = []
    for index, item in enumerate(source if isinstance(source, list) else [], start=1):
        if not isinstance(item, Mapping):
            invalid.append({"id": f"F{index}", "reason": "record is not an object", "record": item})
            continue
        outcome = OUTCOME_ALIASES.get(_text(item.get("outcome") or item.get("status") or item.get("result")).lower())
        record_id = _text(item.get("id") or item.get("feedback_id")) or f"F{index}"
        if not outcome:
            invalid.append({"id": record_id, "reason": "unknown outcome", "raw_outcome": item.get("outcome") or item.get("status") or item.get("result")})
            continue
        accepted.append(
            {
                "id": record_id,
                "outcome": outcome,
                "reviewer": _text(item.get("reviewer") or item.get("reviewer_id")) or "unassigned",
                "profile": _text(item.get("profile")) or "unknown-profile",
                "insight_id": _text(item.get("insight_id") or item.get("item_id")),
                "weight_delta": _float(item.get("weight_delta", item.get("score_delta"))),
                "received_at": item.get("received_at") or item.get("created_at"),
            }
        )
    accepted.sort(key=lambda row: (row["profile"], row["outcome"], row["id"]))
    invalid.sort(key=lambda row: row["id"])
    return accepted, invalid


def _summary(accepted: list[dict[str, Any]], invalid: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["outcome"] for row in accepted)
    return {
        "received_count": len(accepted) + len(invalid),
        "accepted_count": len(accepted),
        "invalid_count": len(invalid),
        "approved_count": counts["approved"],
        "rejected_count": counts["rejected"],
        "deferred_count": counts["deferred"],
        "completed_count": counts["completed"],
        "failed_count": counts["failed"],
    }


def _profile_totals(accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        grouped[row["profile"]].append(row)
    rows = [{"profile": profile, "outcome_count": len(items), "weight_delta": round(sum(item["weight_delta"] for item in items), 4)} for profile, items in grouped.items()]
    rows.sort(key=lambda row: (-row["outcome_count"], row["profile"]))
    return rows


def _reviewer_queues(accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in accepted:
        if row["outcome"] == "deferred":
            grouped[row["reviewer"]].append(row["id"])
    return [{"reviewer": reviewer, "feedback_ids": sorted(ids), "pending_count": len(ids)} for reviewer, ids in sorted(grouped.items())]


def _weight_candidates(accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in accepted if row["outcome"] in {"approved", "rejected", "completed", "failed"} and row["weight_delta"] != 0.0]
    rows.sort(key=lambda row: (-abs(row["weight_delta"]), row["profile"], row["id"]))
    return [{"id": row["id"], "profile": row["profile"], "outcome": row["outcome"], "weight_delta": row["weight_delta"]} for row in rows]


def _metadata(payload: Mapping[str, Any], accepted: list[dict[str, Any]], invalid: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "accepted_count": len(accepted), "invalid_count": len(invalid)}


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
