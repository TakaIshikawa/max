"""JSON API renderer for profile signal balance status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import source_metadata

SCHEMA_VERSION = "max.api.profile_signal_balance_status.v1"
KIND = "max.api.profile_signal_balance_status"
REQUIRED_ROLES = ("market", "problem", "solution")


def profile_signal_balance_status_to_json(
    payload: Mapping[str, Any],
    *,
    dominant_role_warning_ratio: float | None = None,
    dominant_role_critical_ratio: float | None = None,
) -> str:
    warn = _ratio(dominant_role_warning_ratio if dominant_role_warning_ratio is not None else payload.get("dominant_role_warning_ratio"), 0.7)
    critical = _ratio(dominant_role_critical_ratio if dominant_role_critical_ratio is not None else payload.get("dominant_role_critical_ratio"), 0.9)
    rows = _rows(payload, warn, critical)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, warn, critical), "rows": rows, "metadata": source_metadata(payload, profile_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warn: float, critical: float) -> list[dict[str, Any]]:
    source = payload.get("signals") if isinstance(payload.get("signals"), list) else payload.get("items")
    grouped: dict[str, dict[str, int]] = {}
    for item in [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []:
        profile = _text(item.get("profile_id") or item.get("profile"), "unspecified")
        role = _text(item.get("role") or item.get("signal_role"), "unknown").lower()
        if role not in REQUIRED_ROLES:
            role = "unknown"
        grouped.setdefault(profile, {role: 0 for role in (*REQUIRED_ROLES, "unknown")})[role] += 1
    rows = [_row(profile, counts, warn, critical) for profile, counts in grouped.items()]
    return sorted(rows, key=lambda row: (row["severity_rank"], row["profile_id"]))


def _row(profile: str, counts: Mapping[str, int], warn: float, critical: float) -> dict[str, Any]:
    total_known = sum(counts[role] for role in REQUIRED_ROLES)
    dominant_role = max(REQUIRED_ROLES, key=lambda role: (counts[role], role)) if total_known else None
    dominant_ratio = round(counts[dominant_role] / total_known, 4) if dominant_role and total_known else 0.0
    missing = [role for role in REQUIRED_ROLES if counts[role] == 0]
    severity = "critical" if missing or dominant_ratio >= critical else "warn" if dominant_ratio >= warn else "healthy"
    return {"profile_id": profile, "role_counts": dict(counts), "missing_roles": missing, "dominant_role": dominant_role, "dominant_role_ratio": dominant_ratio, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], warn: float, critical: float) -> dict[str, Any]:
    severity = "critical" if any(row["severity"] == "critical" for row in rows) else "warn" if any(row["severity"] == "warn" for row in rows) else "healthy"
    return {"severity": severity, "profile_count": len(rows), "unbalanced_count": sum(1 for row in rows if row["severity"] != "healthy"), "dominant_role_warning_ratio": warn, "dominant_role_critical_ratio": critical}


def _ratio(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number > 1:
        number /= 100
    return round(min(max(number, 0.0), 1.0), 4)


def _text(value: Any, default: str) -> str:
    return " ".join(str(value).strip().split()) if value not in (None, "") else default
