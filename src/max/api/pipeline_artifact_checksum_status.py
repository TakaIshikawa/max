"""JSON API renderer for pipeline artifact checksum status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.pipeline_artifact_checksum_status.v1"
KIND = "max.api.pipeline_artifact_checksum_status"
RANK = {"mismatch": 0, "missing_checksum": 1, "stale_manifest": 2, "unverified": 3, "verified": 4}


def pipeline_artifact_checksum_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_hours = max(0, int_or_zero(payload.get("manifest_stale_hours") or payload.get("stale_manifest_hours") or 24))
    rows = [_artifact(row, i, checked_at, stale_hours) for i, row in enumerate(_artifact_rows(payload), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["status"]], row["artifact_id"].casefold()))
    counts = {name + "_count": sum(1 for row in rows if row["status"] == name) for name in RANK}
    status = "critical" if counts["mismatch_count"] else ("warning" if any(counts[key] for key in ("missing_checksum_count", "stale_manifest_count", "unverified_count")) else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"artifact_count": len(rows), **counts}, "problem_artifacts": [row for row in rows if row["status"] != "verified"], "artifacts": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _artifact(item: Mapping[str, Any], index: int, as_of: datetime, stale_hours: int) -> dict[str, Any]:
    expected = _text(item.get("expected_checksum") or item.get("checksum") or item.get("expected_digest"))
    actual = _text(item.get("actual_checksum") or item.get("actual_digest") or item.get("observed_checksum"))
    verified_at = parse_datetime(item.get("verified_at") or item.get("manifest_verified_at") or item.get("checked_at"))
    age = round((as_of - verified_at).total_seconds() / 3600, 2) if verified_at else None
    missing = not expected
    mismatch = bool(expected and actual and expected != actual)
    stale = age is not None and age > stale_hours
    unverified = not bool(item.get("verified")) and not actual and not mismatch and not missing
    status = "mismatch" if mismatch else ("missing_checksum" if missing else ("stale_manifest" if stale else ("unverified" if unverified else "verified")))
    return {"artifact_id": _text(item.get("artifact_id") or item.get("id")) or f"artifact-{index}", "run_id": _text(item.get("run_id")) or None, "stage": _text(item.get("stage")) or None, "expected_checksum": expected or None, "actual_checksum": actual or None, "verified_at": _stamp(verified_at) if verified_at else None, "manifest_age_hours": age, "status": status, "recommended_action": "investigate checksum mismatch" if mismatch else ("publish artifact checksum" if missing else ("refresh stale checksum manifest" if stale else ("verify artifact checksum" if unverified else "continue monitoring")))}


def _artifact_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = list_of_maps(payload.get("artifacts") or payload.get("items") or payload.get("rows"))
    if direct:
        return direct
    rows: list[Mapping[str, Any]] = []
    for stage in list_of_maps(payload.get("stages")):
        for artifact in list_of_maps(stage.get("artifacts") or stage.get("items")):
            merged = dict(artifact)
            merged.setdefault("stage", stage.get("stage") or stage.get("stage_name") or stage.get("name"))
            merged.setdefault("run_id", stage.get("run_id"))
            rows.append(merged)
    manifest = payload.get("manifest")
    if isinstance(manifest, Mapping):
        rows.extend(list_of_maps(manifest.get("artifacts") or manifest.get("items")))
    return rows


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
