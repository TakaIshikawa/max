"""Profile/source quota utilization export report."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_source_quota_utilization_report.v1"
KIND = "max.profile_source_quota_utilization_report"


def generate_profile_source_quota_utilization_report(
    records: Iterable[Mapping[str, Any]],
    quota_by_profile_source: Mapping[Any, Any] | None = None,
) -> dict[str, Any]:
    """Group usage records by profile/source and attach quota utilization."""
    usage: dict[tuple[str, str], int] = defaultdict(int)
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        profile = _text(raw.get("profile") or raw.get("profile_id")) or "default"
        source = _text(raw.get("source") or raw.get("source_adapter") or raw.get("adapter")) or "unknown-source"
        usage[(profile, source)] += _int(raw.get("used") or raw.get("usage") or raw.get("count") or raw.get("tokens"))

    quotas = quota_by_profile_source or {}
    rows = [_row(profile, source, used, _quota(quotas, profile, source)) for (profile, source), used in usage.items()]
    rows.sort(
        key=lambda row: (
            -(row["utilization_pct"] if row["utilization_pct"] is not None else -1),
            row["profile"].casefold(),
            row["source"].casefold(),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "row_count": len(rows),
            "total_used": sum(row["used"] for row in rows),
            "missing_quota_count": sum(1 for row in rows if row["quota"] is None),
        },
        "quota_rows": rows,
    }


def _row(profile: str, source: str, used: int, quota: int | None) -> dict[str, Any]:
    remaining = None if quota is None else quota - used
    utilization = None if quota in (None, 0) else round((used / quota) * 100, 2)
    return {
        "profile": profile,
        "source": source,
        "used": used,
        "quota": quota,
        "remaining": remaining,
        "utilization_pct": utilization,
        "quota_missing": quota is None,
    }


def _quota(quotas: Mapping[Any, Any], profile: str, source: str) -> int | None:
    candidates = [
        (profile, source),
        f"{profile}:{source}",
        f"{profile}/{source}",
    ]
    for key in candidates:
        if key in quotas:
            return _optional_int(quotas[key])
    nested = quotas.get(profile)
    if isinstance(nested, Mapping) and source in nested:
        return _optional_int(nested[source])
    return None


def _optional_int(value: Any) -> int | None:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    parsed = _optional_int(value)
    return parsed if parsed is not None else 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
