"""JSON API renderer for pipeline run handoff digests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.pipeline_run_handoff_digest.v1"
KIND = "max.api.pipeline_run_handoff_digest"


def pipeline_run_handoff_digest_to_json(payload: Mapping[str, Any]) -> str:
    """Render pipeline run handoff digest data as deterministic API JSON."""
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_summary": _run_summary(payload),
        "stage_statuses": _stage_statuses(payload),
        "blockers": _blockers(payload),
        "next_actions": _next_actions(payload),
        "owners": _owners(payload),
        "metadata": _metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _run_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    run = _mapping(payload.get("run"))
    summary = _mapping(payload.get("summary"))
    budget = _mapping(payload.get("budget"))
    source = _mapping(payload.get("run_summary"))

    return {
        "run_id": source.get("run_id") or source.get("id") or run.get("id"),
        "status": source.get("status") or run.get("status"),
        "profile": source.get("profile") or run.get("profile"),
        "domain": source.get("domain") or run.get("domain"),
        "started_at": source.get("started_at") or run.get("started_at"),
        "completed_at": source.get("completed_at") or run.get("completed_at"),
        "idea_count": _int_or_zero(source.get("idea_count", summary.get("idea_count"))),
        "warning_count": _int_or_zero(source.get("warning_count", summary.get("warning_count"))),
        "next_action_count": _int_or_zero(
            source.get("next_action_count", summary.get("next_action_count"))
        ),
        "budget": {
            "model": budget.get("model"),
            "total_tokens": _int_or_zero(budget.get("total_tokens")),
            "estimated_cost_usd": _float_or_zero(budget.get("estimated_cost_usd")),
        },
    }


def _stage_statuses(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("stage_statuses"), list):
        rows = [_stage_row(item) for item in payload["stage_statuses"] if isinstance(item, Mapping)]
    else:
        rows = []
        stage_counts = _mapping(payload.get("stage_counts"))
        for name in sorted(stage_counts):
            status = "reported" if stage_counts.get(name) not in (None, 0, "") else "empty"
            rows.append(
                {
                    "stage": str(name),
                    "status": status,
                    "value": stage_counts.get(name),
                    "details": {},
                }
            )

        budget = _mapping(payload.get("budget"))
        for item in _list_of_maps(budget.get("stages")):
            rows.append(
                {
                    "stage": str(item.get("stage") or "unknown"),
                    "status": str(item.get("status") or "reported"),
                    "value": item.get("total_tokens"),
                    "details": {
                        "input_tokens": _int_or_zero(item.get("input_tokens")),
                        "output_tokens": _int_or_zero(item.get("output_tokens")),
                        "estimated_cost_usd": _float_or_zero(item.get("estimated_cost_usd")),
                    },
                }
            )

    return sorted(rows, key=lambda row: (str(row.get("stage") or ""), str(row.get("status") or "")))


def _stage_row(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": str(item.get("stage") or item.get("name") or "unknown"),
        "status": item.get("status"),
        "value": item.get("value"),
        "details": dict(_mapping(item.get("details"))),
    }


def _blockers(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("blockers")
    if not isinstance(source, list):
        source = payload.get("warnings")

    rows = []
    for index, item in enumerate(source if isinstance(source, list) else [], start=1):
        if isinstance(item, Mapping):
            rows.append(
                {
                    "id": item.get("id") or f"B{index}",
                    "severity": item.get("severity"),
                    "message": item.get("message") or item.get("description") or item.get("title"),
                    "owner": item.get("owner"),
                    "stage": item.get("stage"),
                }
            )
        else:
            rows.append(
                {
                    "id": f"B{index}",
                    "severity": None,
                    "message": str(item),
                    "owner": None,
                    "stage": None,
                }
            )
    return rows


def _next_actions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_as_list(payload.get("next_actions")), start=1):
        if isinstance(item, Mapping):
            rows.append(
                {
                    "id": item.get("id") or f"A{index}",
                    "action": item.get("action") or item.get("title") or item.get("description"),
                    "owner": item.get("owner"),
                    "due_at": item.get("due_at") or item.get("due_date"),
                    "status": item.get("status"),
                }
            )
        else:
            rows.append(
                {
                    "id": f"A{index}",
                    "action": str(item),
                    "owner": None,
                    "due_at": None,
                    "status": None,
                }
            )
    return rows


def _owners(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    explicit = _as_list(payload.get("owners"))
    rows = [_owner_row(item, index) for index, item in enumerate(explicit, start=1)]
    if rows:
        return rows

    owners: dict[str, dict[str, Any]] = {}
    for action in _next_actions(payload):
        owner = action.get("owner")
        if owner:
            owners.setdefault(
                str(owner),
                {"owner": str(owner), "role": None, "responsibilities": []},
            )["responsibilities"].append(str(action.get("action") or "next_action"))
    for blocker in _blockers(payload):
        owner = blocker.get("owner")
        if owner:
            owners.setdefault(
                str(owner),
                {"owner": str(owner), "role": None, "responsibilities": []},
            )["responsibilities"].append(str(blocker.get("message") or "blocker"))
    return sorted(owners.values(), key=lambda row: str(row.get("owner") or ""))


def _owner_row(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return {
            "owner": item.get("owner") or item.get("name") or item.get("email"),
            "role": item.get("role"),
            "responsibilities": [str(value) for value in _as_list(item.get("responsibilities"))],
        }
    return {"owner": str(item), "role": None, "responsibilities": []}


def _metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version")
        or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "stage_status_count": len(_stage_statuses(payload)),
        "blocker_count": len(_blockers(payload)),
        "next_action_count": len(_next_actions(payload)),
        "owner_count": len(_owners(payload)),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
