"""Embedding dimension mismatch export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.embedding_dimension_mismatch_report.v1"
KIND = "max.embedding_dimension_mismatch_report"


def generate_embedding_dimension_mismatch_report(records: Iterable[dict[str, Any]], *, expected_dimension: int) -> dict[str, Any]:
    expected = _int(expected_dimension)
    findings = []
    checked = 0
    missing = 0
    for raw in records:
        checked += 1
        observed = _dimension(raw)
        if observed is None:
            missing += 1
        if observed != expected:
            findings.append(
                {
                    "object_id": _text(raw.get("object_id") or raw.get("id")) or "unknown-object",
                    "source_type": _text(raw.get("source_type") or raw.get("type")) or "unknown-source",
                    "observed_dimension": observed,
                    "expected_dimension": expected,
                    "issue_type": "missing_vector" if observed is None else "dimension_mismatch",
                    "recommendation": "Regenerate and reindex embedding with the configured dimension.",
                }
            )
    findings.sort(key=lambda row: (row["issue_type"], row["source_type"].lower(), row["object_id"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "checked_count": checked,
            "mismatch_count": sum(1 for row in findings if row["issue_type"] == "dimension_mismatch"),
            "missing_vector_count": missing,
            "expected_dimension": expected,
        },
        "findings": findings,
    }


def _dimension(raw: dict[str, Any]) -> int | None:
    if "dimension" in raw:
        return _int(raw.get("dimension"))
    if "vector_dimension" in raw:
        return _int(raw.get("vector_dimension"))
    vector = raw.get("vector") or raw.get("embedding")
    if isinstance(vector, list):
        return len(vector)
    return None


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

