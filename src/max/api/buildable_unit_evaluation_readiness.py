"""JSON API renderer for buildable unit evaluation readiness."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.buildable_unit_evaluation_readiness.v1"
KIND = "max.api.buildable_unit_evaluation_readiness"
STATUS_RANK = {"blocked": 0, "needs_evidence": 1, "ready": 2}


def buildable_unit_evaluation_readiness_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    units = _units(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(units),
        "buildable_units": units,
        "blockers": [row for row in units if row["missing_fields"]],
        "metadata": _metadata(payload, units, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _units(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("units") if isinstance(payload.get("units"), list) else payload.get("buildable_units")
    rows = [_unit(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["unit_id"]))
    return rows


def _unit(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    problem = _bool(item.get("problem_present", item.get("has_problem")))
    solution = _bool(item.get("solution_present", item.get("has_solution")))
    stack = _bool(item.get("stack_present", item.get("has_stack")))
    evidence_count = _int(item.get("evidence_count", item.get("evidence")))
    missing = [name for name, present in (("problem", problem), ("solution", solution), ("stack", stack), ("evidence", evidence_count > 0)) if not present]
    status = "blocked" if any(field in missing for field in ("problem", "solution", "stack")) else ("needs_evidence" if "evidence" in missing else "ready")
    return {
        "unit_id": _text(item.get("unit_id") or item.get("id")) or f"unit-{index}",
        "profile": _text(item.get("profile")) or "unknown-profile",
        "problem_present": problem,
        "solution_present": solution,
        "stack_present": stack,
        "evidence_count": evidence_count,
        "evaluation_score": _score(item.get("evaluation_score", item.get("score"))),
        "recommendation": _text(item.get("recommendation")),
        "status": status,
        "missing_fields": missing,
    }


def _summary(units: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in units)
    return {
        "unit_count": len(units),
        "ready_count": counts["ready"],
        "blocked_count": counts["blocked"],
        "needs_evidence_count": counts["needs_evidence"],
        "average_evaluation_score": round(sum(row["evaluation_score"] for row in units) / len(units), 4) if units else 0.0,
    }


def _metadata(payload: Mapping[str, Any], units: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "unit_count": len(units)}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _int(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value or 0), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
