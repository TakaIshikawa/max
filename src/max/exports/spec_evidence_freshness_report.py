"""Spec evidence freshness export report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_evidence_freshness_report.v1"
KIND = "max.spec_evidence_freshness_report"


def generate_spec_evidence_freshness_report(records: Iterable[dict[str, Any]], *, as_of: datetime, stale_after_days: int = 30, stale_threshold: int = 0) -> dict[str, Any]:
    now = _dt(as_of) or datetime.now(timezone.utc)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile")) or "default"
        spec_id = _text(raw.get("spec_id") or raw.get("id")) or "unknown-spec"
        group = groups.setdefault((profile, spec_id), {"ages": [], "stale": []})
        evidence = _items(raw.get("evidence") or raw.get("evidence_items")) or [raw]
        for index, item in enumerate(evidence, start=1):
            timestamp = _dt(item.get("evidence_at") or item.get("observed_at") or item.get("created_at") or item.get("timestamp")) if isinstance(item, dict) else None
            if timestamp is None:
                continue
            age = max(0, (now - timestamp).days)
            group["ages"].append(age)
            if age > stale_after_days:
                evidence_id = _text(item.get("evidence_id") or item.get("signal_id") or item.get("id")) if isinstance(item, dict) else ""
                group["stale"].append(evidence_id or f"evidence-{index}")
    rows = []
    for (profile, spec_id), group in groups.items():
        ages = group["ages"]
        stale_ids = sorted(group["stale"], key=str.lower)
        rows.append({"profile": profile, "spec_id": spec_id, "evidence_count": len(ages), "stale_count": len(stale_ids), "newest_age_days": min(ages) if ages else None, "oldest_age_days": max(ages) if ages else None, "stale_evidence_ids": stale_ids, "status": "stale" if len(stale_ids) > stale_threshold else "fresh"})
    rows.sort(key=lambda row: (row["profile"].lower(), row["spec_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "stale_count": sum(1 for row in rows if row["status"] == "stale"), "stale_after_days": stale_after_days, "stale_threshold": stale_threshold}, "rows": rows}


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
