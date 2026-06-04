"""JSON API renderer for signal annotation role imbalance status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_annotation_role_imbalance_status.v1"
KIND = "max.api.signal_annotation_role_imbalance_status"
REQUIRED_ROLES = ("market", "problem", "solution")
STATUS_RANK = {"critical": 0, "warning": 1, "insufficient_data": 2, "ok": 3}


def signal_annotation_role_imbalance_status_to_json(payload: Mapping[str, Any], *, dominance_threshold: float = 0.7) -> str:
    grouped: dict[tuple[str, str], list[str]] = {}
    for item in _items(payload):
        key = (_text(item.get("source")) or "unknown", _text(item.get("profile")) or "default")
        grouped.setdefault(key, []).append(_text(item.get("role") or item.get("annotation_role")).casefold() or "unknown")
    rows = [_row(source, profile, roles, dominance_threshold) for (source, profile), roles in grouped.items()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["dominant_role_ratio"], row["source"], row["profile"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"group_count": len(rows), "imbalanced_group_count": sum(1 for row in rows if row["status"] in {"critical", "warning"}), "unknown_role_count": sum(row["unknown_role_count"] for row in rows)}, "role_rows": rows, "metadata": source_metadata(payload, group_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("annotations") or payload.get("rows") or payload.get("items"))


def _row(source: str, profile: str, roles: list[str], threshold: float) -> dict[str, Any]:
    counts = Counter(roles)
    known_total = sum(counts[role] for role in REQUIRED_ROLES)
    ratios = {role: round(counts[role] / known_total, 4) if known_total else 0.0 for role in REQUIRED_ROLES}
    missing = [role for role in REQUIRED_ROLES if counts[role] == 0]
    dominant = max(REQUIRED_ROLES, key=lambda role: counts[role])
    dominant_ratio = ratios[dominant]
    status = "insufficient_data" if not roles else "critical" if missing else "warning" if dominant_ratio >= threshold else "ok"
    return {"source": source, "profile": profile, "role_counts": {role: counts[role] for role in REQUIRED_ROLES}, "role_ratios": ratios, "unknown_role_count": sum(count for role, count in counts.items() if role not in REQUIRED_ROLES), "missing_roles": missing, "dominant_role": dominant if known_total else None, "dominant_role_ratio": dominant_ratio, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
