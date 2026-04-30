"""Reusable serializers for analysis exports."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    from max.types.buildable_unit import BuildableUnit
    from max.types.evaluation import UtilityEvaluation


IDEA_EXPORT_FIELDS = (
    "id",
    "title",
    "one_liner",
    "category",
    "domain",
    "status",
    "evaluation_score",
    "recommendation",
    "latest_feedback_outcome",
    "latest_feedback_reason",
    "latest_feedback_score",
    "latest_feedback_at",
    "quality_score",
    "novelty_score",
    "usefulness_score",
    "rejection_tags",
    "inspiring_insight_ids",
    "evidence_signal_ids",
    "source_idea_ids",
    "created_at",
    "updated_at",
)

IDEA_CSV_EXPORT_FIELDS = (
    "id",
    "title",
    "domain",
    "status",
    "category",
    "recommendation",
    "overall_score",
    "source_adapters",
    "evidence_signal_count",
    "created_at",
    "updated_at",
)


def idea_export_record(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    latest_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize one idea into the stable export summary shape."""
    return {
        "id": unit.id,
        "title": unit.title,
        "one_liner": unit.one_liner,
        "category": str(unit.category),
        "domain": unit.domain,
        "status": unit.status,
        "evaluation_score": evaluation.overall_score if evaluation else None,
        "recommendation": evaluation.recommendation if evaluation else None,
        "latest_feedback_outcome": latest_feedback.get("outcome") if latest_feedback else None,
        "latest_feedback_reason": latest_feedback.get("reason") if latest_feedback else None,
        "latest_feedback_score": latest_feedback.get("approval_score") if latest_feedback else None,
        "latest_feedback_at": latest_feedback.get("created_at") if latest_feedback else None,
        "quality_score": unit.quality_score,
        "novelty_score": unit.novelty_score,
        "usefulness_score": unit.usefulness_score,
        "rejection_tags": list(unit.rejection_tags),
        "inspiring_insight_ids": list(unit.inspiring_insights),
        "evidence_signal_ids": list(unit.evidence_signals),
        "source_idea_ids": list(unit.source_idea_ids),
        "created_at": _as_export_value(unit.created_at),
        "updated_at": _as_export_value(unit.updated_at),
    }


def idea_export_records(
    units: Iterable[BuildableUnit],
    *,
    get_evaluation: Callable[[str], UtilityEvaluation | None],
    get_latest_feedback: Callable[[str], dict[str, Any] | None],
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """Build export records for ideas, optionally filtering by evaluation score."""
    records: list[dict[str, Any]] = []
    for unit in units:
        evaluation = get_evaluation(unit.id)
        if min_score is not None:
            if evaluation is None or evaluation.overall_score < min_score:
                continue
        records.append(idea_export_record(unit, evaluation, get_latest_feedback(unit.id)))
    return records


def render_idea_export(records: Iterable[dict[str, Any]], *, fmt: str) -> str:
    """Render idea export records as JSON Lines or CSV."""
    rows = list(records)
    if fmt == "jsonl":
        return "".join(json.dumps(row, default=_as_export_value) + "\n" for row in rows)
    if fmt == "csv":
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=IDEA_CSV_EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            csv_row = _idea_csv_record(row)
            writer.writerow({field: _csv_value(csv_row.get(field)) for field in IDEA_CSV_EXPORT_FIELDS})
        return output.getvalue()
    raise ValueError(f"Unsupported idea export format: {fmt}")


def write_idea_export(path: Path, records: Iterable[dict[str, Any]], *, fmt: str) -> None:
    """Write idea export records to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_idea_export(records, fmt=fmt), encoding="utf-8")


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    return _as_export_value(value)


def _as_export_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _idea_csv_record(row: dict[str, Any]) -> dict[str, Any]:
    evidence_signal_ids = row.get("evidence_signal_ids")
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "domain": row.get("domain"),
        "status": row.get("status"),
        "category": row.get("category"),
        "recommendation": row.get("recommendation"),
        "overall_score": row.get("overall_score", row.get("evaluation_score")),
        "source_adapters": _joined_list(row.get("source_adapters")),
        "evidence_signal_count": len(evidence_signal_ids) if isinstance(evidence_signal_ids, list) else "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _joined_list(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        items = value.keys()
    elif isinstance(value, str):
        return value
    else:
        try:
            items = list(value)
        except TypeError:
            return str(value)
    return ", ".join(sorted(str(item) for item in items))
