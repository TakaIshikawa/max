"""Generate bounded ingestion replay window plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.ingestion_replay_window_plan.v1"
KIND = "max.spec.ingestion_replay_window_plan"


def generate_ingestion_replay_window_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "ingestion_replay_window")
    windows = sorted((_window(row, i, evidence_ids) for i, row in enumerate(_rows(hints) or _rows(spec), 1)), key=lambda row: (row["source"], row["start_at"]))
    _mark_overlaps(windows)
    risky = [row for row in windows if row["risk_level"] in {"high", "critical"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {"status": "no_replay_needed" if not windows else "review", "window_count": len(windows), "high_risk_count": len(risky)},
        "replay_windows": windows,
        "source_groups": [{"source": source, "window_ids": [row["id"] for row in windows if row["source"] == source]} for source in sorted({row["source"] for row in windows})],
        "risk_guidance": [{"id": f"IRR{i}", "window_id": row["id"], "guidance": "run dry-run sample, dedupe by external id, and cap replay volume", "evidence_reference_ids": evidence_ids} for i, row in enumerate(risky, 1)],
        "validation_checks": [{"id": "IRV1", "check": "compare replayed signal count, duplicate count, and checkpoint movement", "evidence_reference_ids": evidence_ids}],
        "verification_gates": [{"id": "IRG1", "check": "no replay writes occur outside requested source windows", "evidence_reference_ids": evidence_ids}],
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("windows", "replay_windows", "requests"):
        value = source.get(key) if isinstance(source, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _window(row: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    start = compact(row.get("start_at") or row.get("start"))
    end = compact(row.get("end_at") or row.get("end"))
    hours = round((_parse(end) - _parse(start)).total_seconds() / 3600, 2) if start and end else 0.0
    volume = _int(row.get("estimated_records") or row.get("volume"))
    risk = "high" if hours > 168 or volume > 10000 else "medium" if hours > 24 or volume > 1000 else "low"
    return {"id": f"IRW{index}", "source": compact(row.get("source")) or "unknown", "start_at": start, "end_at": end, "duration_hours": hours, "estimated_records": volume, "risk_level": risk, "overlap": False, "evidence_reference_ids": evidence_ids}


def _mark_overlaps(windows: list[dict[str, Any]]) -> None:
    for i, left in enumerate(windows):
        for right in windows[i + 1:]:
            if left["source"] == right["source"] and left["start_at"] < right["end_at"] and right["start_at"] < left["end_at"]:
                left["overlap"] = right["overlap"] = True
                left["risk_level"] = right["risk_level"] = "high"


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
