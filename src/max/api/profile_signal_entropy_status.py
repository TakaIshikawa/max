"""JSON API renderer for profile signal entropy status."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.profile_signal_entropy_status.v1"
KIND = "max.api.profile_signal_entropy_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def profile_signal_entropy_status_to_json(payload: Mapping[str, Any], *, warning_entropy: float = 1.0, critical_entropy: float = 0.5) -> str:
    rows = _rows(payload, warning_entropy, critical_entropy)
    lowest = min(rows, key=lambda row: (row["entropy"], row["profile"]), default=None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_profiles": len(rows), "critical_profiles": sum(1 for row in rows if row["status"] == "critical"), "warning_profiles": sum(1 for row in rows if row["status"] == "warning"), "lowest_entropy_profile": lowest["profile"] if lowest else None}, "profile_rows": rows, "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: float, critical: float) -> list[dict[str, Any]]:
    source = payload.get("profiles") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "profile": value.get("profile") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["entropy"], row["profile"]))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    counts = item.get("source_counts") or item.get("sources") or {}
    normalized = {str(key): max(0, int_or_zero(value)) for key, value in counts.items()} if isinstance(counts, Mapping) else {}
    total = sum(normalized.values())
    entropy = -sum((count / total) * math.log2(count / total) for count in normalized.values() if total and count > 0) if total else 0.0
    dominant_source = max(normalized, key=lambda key: (normalized[key], key), default=None)
    dominant_share = normalized[dominant_source] / total if dominant_source and total else 0.0
    status = "critical" if entropy <= critical else "warning" if entropy <= warning else "ok"
    return {"profile": _text(item.get("profile") or item.get("name")) or f"profile-{index}", "source_counts": dict(sorted(normalized.items())), "total_signals": total, "entropy": round(entropy, 4), "dominant_source": dominant_source, "dominant_share": round(dominant_share, 4), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
