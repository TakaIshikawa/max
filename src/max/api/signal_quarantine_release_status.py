"""JSON API renderer for signal quarantine release status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import source_metadata, strings

SCHEMA_VERSION = "max.api.signal_quarantine_release_status.v1"
KIND = "max.api.signal_quarantine_release_status"


def signal_quarantine_release_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "release_eligible_signals": [row for row in rows if row["release_eligible"]], "metadata": source_metadata(payload, quarantined_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("signals") if isinstance(payload.get("signals"), list) else payload.get("items")
    rows = [_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (not row["release_eligible"], row["source"], row["signal_id"]))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    checks = strings(item.get("blocking_checks"))
    state = _bucket(item.get("review_state"), "pending")
    eligible = state == "approved" and not checks
    return {"signal_id": _text(item.get("signal_id")) or f"signal-{index}", "source": _bucket(item.get("source"), "unknown_source"), "reason": _bucket(item.get("reason"), "unspecified"), "quarantined_at": _text(item.get("quarantined_at")) or None, "review_state": state, "release_eligible": eligible, "blocking_checks": checks, "release_action": _text(item.get("release_action")) or ("release" if eligible else "hold")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "release_ready" if any(row["release_eligible"] for row in rows) else "blocked", "quarantined_count": len(rows), "release_eligible_count": sum(1 for row in rows if row["release_eligible"]), "blocked_count": sum(1 for row in rows if not row["release_eligible"]), "reasons": sorted({row["reason"] for row in rows})}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
