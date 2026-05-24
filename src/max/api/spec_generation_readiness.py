"""JSON API renderer for spec generation readiness."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.spec_generation_readiness.v1"
KIND = "max.api.spec_generation_readiness"


def spec_generation_readiness_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    units = _units(payload)
    ready = [unit for unit in units if unit["readiness"] == "ready"]
    blocked = [unit for unit in units if unit["readiness"] != "ready"]
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(units),
        "ready_units": ready,
        "blocked_units": blocked,
        "readiness_buckets": _buckets(units),
        "owner_hints": _owner_hints(units),
        "next_actions": _next_actions(blocked),
        "metadata": _metadata(payload, units, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _units(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("units") if isinstance(payload.get("units"), list) else payload.get("buildable_units")
    rows = [_unit(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["readiness_rank"], row["unit_id"], row["title"]))
    return rows


def _unit(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    evidence_count = _int(item.get("evidence_count", len(_as_list(item.get("evidence")))))
    recommendation = _text(item.get("evaluation_recommendation") or item.get("recommendation")).lower()
    missing = _missing(item)
    explicit = _text(item.get("status") or item.get("readiness")).lower()
    readiness = _readiness(explicit, evidence_count, recommendation, missing)
    return {
        "unit_id": _text(item.get("unit_id") or item.get("id")) or f"U{index}",
        "title": _text(item.get("title") or item.get("name")) or f"Buildable unit {index}",
        "owner": _text(item.get("owner")) or None,
        "evidence_count": evidence_count,
        "evaluation_recommendation": recommendation or "unknown",
        "missing_inputs": missing,
        "readiness": readiness,
        "readiness_rank": {"ready": 0, "needs_review": 1, "blocked": 2}.get(readiness, 3),
    }


def _readiness(explicit: str, evidence_count: int, recommendation: str, missing: list[str]) -> str:
    if explicit in {"ready", "blocked", "needs_review"}:
        return explicit
    if missing or recommendation in {"reject", "rejected", "do_not_build"}:
        return "blocked"
    if evidence_count <= 0 or recommendation in {"review", "needs_review", "unknown", ""}:
        return "needs_review"
    return "ready"


def _summary(units: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(unit["readiness"] for unit in units)
    return {"unit_count": len(units), "ready_count": counts["ready"], "blocked_count": counts["blocked"], "needs_review_count": counts["needs_review"]}


def _buckets(units: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(unit["readiness"] for unit in units)
    return {"ready": counts["ready"], "needs_review": counts["needs_review"], "blocked": counts["blocked"]}


def _owner_hints(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for unit in units:
        if unit["owner"] and unit["readiness"] != "ready":
            grouped[str(unit["owner"])].append(unit["unit_id"])
    return [{"owner": owner, "unit_ids": sorted(ids), "blocked_count": len(ids)} for owner, ids in sorted(grouped.items())]


def _next_actions(blocked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": f"complete-{unit['unit_id']}", "unit_id": unit["unit_id"], "action": "Complete missing inputs", "missing_inputs": unit["missing_inputs"]}
        for unit in blocked
    ]


def _metadata(payload: Mapping[str, Any], units: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "unit_count": len(units)}


def _missing(item: Mapping[str, Any]) -> list[str]:
    value = item.get("missing_inputs", item.get("missing_fields", item.get("missing")))
    return sorted({_text(reason).lower().replace(" ", "_") for reason in _as_list(value) if _text(reason)})


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
