"""JSON API renderer for idea duplicate risk."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.idea_duplicate_risk.v1"
KIND = "max.api.idea_duplicate_risk"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def idea_duplicate_risk_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    ideas = _ideas(payload)
    pairs = _pairs(payload, ideas)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(ideas, pairs),
        "ideas": ideas,
        "top_risky_pairs": pairs[: _int(payload.get("limit", payload.get("top_n", 10)), 10)],
        "profile_counts": _profile_counts(ideas, pairs),
        "metadata": _metadata(payload, ideas, pairs, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _ideas(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("ideas") if isinstance(payload.get("ideas"), list) else payload.get("items")
    rows = [_idea(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: row["idea_id"])
    return rows


def _idea(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    evidence_ids = _ids(item.get("evidence_ids", item.get("evidence", item.get("evidence_items"))))
    return {
        "idea_id": _text(item.get("idea_id") or item.get("id")) or f"idea-{index}",
        "title": _text(item.get("title") or item.get("name")),
        "profile": _bucket(item.get("profile") or item.get("profile_id"), "unknown-profile"),
        "evidence_ids": evidence_ids,
        "evidence_count": len(evidence_ids),
    }


def _pairs(payload: Mapping[str, Any], ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["idea_id"]: row for row in ideas}
    source = payload.get("pairs") if isinstance(payload.get("pairs"), list) else payload.get("similarities")
    rows = []
    for item in source if isinstance(source, list) else []:
        if not isinstance(item, Mapping):
            continue
        left_id = _text(item.get("idea_a") or item.get("left") or item.get("source_id") or item.get("idea_id_a"))
        right_id = _text(item.get("idea_b") or item.get("right") or item.get("target_id") or item.get("idea_id_b"))
        if not left_id or not right_id:
            pair_ids = item.get("idea_ids")
            if isinstance(pair_ids, list) and len(pair_ids) >= 2:
                left_id, right_id = _text(pair_ids[0]), _text(pair_ids[1])
        if not left_id or not right_id or left_id == right_id:
            continue
        left, right = by_id.get(left_id, {"profile": "unknown-profile", "evidence_ids": []}), by_id.get(right_id, {"profile": "unknown-profile", "evidence_ids": []})
        left_id, right_id = sorted([left_id, right_id])
        shared = sorted(set(_ids(item.get("overlapping_evidence_ids", item.get("shared_evidence_ids")))) or (set(left["evidence_ids"]) & set(right["evidence_ids"])))
        similarity = _ratio(item.get("similarity", item.get("score")))
        status = _status(similarity, len(shared))
        rows.append(
            {
                "idea_ids": [left_id, right_id],
                "profiles": sorted({left["profile"], right["profile"]}),
                "similarity": similarity,
                "shared_evidence_ids": shared,
                "shared_evidence_count": len(shared),
                "status": status,
            }
        )
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["similarity"], row["idea_ids"][0], row["idea_ids"][1]))
    return rows


def _status(similarity: float, shared_count: int) -> str:
    if similarity >= 0.95 or (similarity >= 0.9 and shared_count >= 3):
        return "critical"
    if similarity >= 0.85 or (similarity >= 0.75 and shared_count >= 2):
        return "high"
    if similarity >= 0.65 or shared_count >= 1:
        return "medium"
    return "low"


def _profile_counts(ideas: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    idea_counts = Counter(row["profile"] for row in ideas)
    risky: Counter[str] = Counter()
    critical: Counter[str] = Counter()
    for pair in pairs:
        if pair["status"] in {"medium", "high", "critical"}:
            risky.update(pair["profiles"])
        if pair["status"] == "critical":
            critical.update(pair["profiles"])
    rows = [{"profile": profile, "idea_count": count, "risky_pair_count": risky[profile], "critical_pair_count": critical[profile]} for profile, count in idea_counts.items()]
    rows.sort(key=lambda row: (-row["critical_pair_count"], -row["risky_pair_count"], row["profile"]))
    return rows


def _summary(ideas: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in pairs)
    overall = "low"
    for status in ("critical", "high", "medium"):
        if counts[status]:
            overall = status
            break
    return {"idea_count": len(ideas), "pair_count": len(pairs), "status": overall, "medium_count": counts["medium"], "high_count": counts["high"], "critical_count": counts["critical"]}


def _metadata(payload: Mapping[str, Any], ideas: list[dict[str, Any]], pairs: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "idea_count": len(ideas), "pair_count": len(pairs)}


def _ids(value: Any) -> list[str]:
    raw: list[Any] = []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, Mapping):
        raw = list(value.values())
    rows = []
    for item in raw:
        if isinstance(item, Mapping):
            text = _text(item.get("evidence_id") or item.get("id"))
        else:
            text = _text(item)
        if text:
            rows.append(text)
    return sorted(set(rows))


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _ratio(value: Any) -> float:
    try:
        return round(min(max(float(value or 0), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
