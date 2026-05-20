"""Feedback learning effectiveness report for evaluation decisions over time."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max.feedback_learning_effectiveness.v1"
KIND = "max.feedback_learning_effectiveness"
CSV_COLUMNS = (
    "bucket",
    "evaluated_count",
    "approval_rate",
    "false_positive_count",
    "false_negative_count",
    "calibration_band",
)
APPROVED_OUTCOMES = {"approved", "published", "success"}
REJECTED_OUTCOMES = {"rejected", "abandoned", "failed"}
POSITIVE_RECOMMENDATIONS = {"strong_yes", "yes"}
NEGATIVE_RECOMMENDATIONS = {"no", "strong_no"}
_BAND_ORDER = {"poor": 0, "mixed": 1, "aligned": 2, "insufficient_data": 3}


@dataclass(frozen=True)
class FeedbackEvaluationRecord:
    unit_id: str
    recommendation: str
    evaluated_at: datetime | str | date | None = None


@dataclass(frozen=True)
class FeedbackOutcomeRecord:
    unit_id: str
    outcome: str
    created_at: datetime | str | date | None = None


@dataclass(frozen=True)
class FeedbackLearningRow:
    bucket: str
    evaluated_count: int
    approval_rate: float
    false_positive_count: int
    false_negative_count: int
    calibration_band: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "evaluated_count": self.evaluated_count,
            "approval_rate": self.approval_rate,
            "false_positive_count": self.false_positive_count,
            "false_negative_count": self.false_negative_count,
            "calibration_band": self.calibration_band,
        }


def build_feedback_learning_effectiveness_report(
    evaluations: Iterable[FeedbackEvaluationRecord | Mapping[str, Any]],
    feedback: Iterable[FeedbackOutcomeRecord | Mapping[str, Any]],
    *,
    bucket: str = "month",
    min_bucket_samples: int = 2,
    improvement_threshold: float = 0.05,
) -> dict[str, Any]:
    """Compare evaluation recommendations against terminal feedback outcomes by time bucket."""
    if bucket not in {"day", "month"}:
        raise ValueError("bucket must be day or month")
    if min_bucket_samples < 1:
        raise ValueError("min_bucket_samples must be at least 1")
    if improvement_threshold < 0:
        raise ValueError("improvement_threshold must be non-negative")

    evaluation_map = {_normalize_evaluation(item).unit_id: _normalize_evaluation(item) for item in evaluations}
    samples: dict[str, list[tuple[FeedbackEvaluationRecord, FeedbackOutcomeRecord]]] = {}
    for raw_feedback in feedback:
        outcome = _normalize_feedback(raw_feedback)
        evaluation = evaluation_map.get(outcome.unit_id)
        if evaluation is None or outcome.outcome not in APPROVED_OUTCOMES | REJECTED_OUTCOMES:
            continue
        bucket_key = _bucket_key(outcome.created_at or evaluation.evaluated_at, bucket)
        samples.setdefault(bucket_key, []).append((evaluation, outcome))

    rows = [_row_for_bucket(key, values, min_bucket_samples) for key, values in samples.items()]
    rows.sort(key=lambda row: row.bucket)
    summary = _summary(rows, improvement_threshold)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "bucket": bucket,
            "min_bucket_samples": min_bucket_samples,
            "improvement_threshold": improvement_threshold,
        },
        "summary": summary,
        "rows": [row.as_dict() for row in rows],
    }


def render_feedback_learning_effectiveness_report(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render feedback learning effectiveness as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported feedback learning effectiveness report format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Feedback Learning Effectiveness",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Buckets: {summary.get('bucket_count', 0)}",
        f"Trend: {summary.get('trend', 'insufficient_data')}",
        f"Improving buckets: {summary.get('improving_bucket_count', 0)}",
        f"Degrading buckets: {summary.get('degrading_bucket_count', 0)}",
        f"Insufficient-data buckets: {summary.get('insufficient_data_bucket_count', 0)}",
        "",
        "## Buckets",
        "",
        "| Bucket | Evaluated | Approval Rate | False Positives | False Negatives | Calibration |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = _sorted_row_maps(report.get("rows"))
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | {} | {:.3f} | {} | {} | {} |".format(
                    row.get("bucket") or "",
                    row.get("evaluated_count", 0),
                    float(row.get("approval_rate") or 0.0),
                    row.get("false_positive_count", 0),
                    row.get("false_negative_count", 0),
                    row.get("calibration_band") or "",
                )
            )
    else:
        lines.append("| none | 0 | 0.000 | 0 | 0 | insufficient_data |")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("rows")):
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _row_for_bucket(
    bucket_key: str,
    samples: list[tuple[FeedbackEvaluationRecord, FeedbackOutcomeRecord]],
    min_bucket_samples: int,
) -> FeedbackLearningRow:
    approved = 0
    false_positive = 0
    false_negative = 0
    for evaluation, feedback in samples:
        is_approved = feedback.outcome in APPROVED_OUTCOMES
        approved += int(is_approved)
        false_positive += int(evaluation.recommendation in POSITIVE_RECOMMENDATIONS and not is_approved)
        false_negative += int(evaluation.recommendation in NEGATIVE_RECOMMENDATIONS and is_approved)
    count = len(samples)
    error_rate = (false_positive + false_negative) / count if count else 1.0
    if count < min_bucket_samples:
        band = "insufficient_data"
    elif error_rate <= 0.1:
        band = "aligned"
    elif error_rate <= 0.35:
        band = "mixed"
    else:
        band = "poor"
    return FeedbackLearningRow(
        bucket=bucket_key,
        evaluated_count=count,
        approval_rate=round(approved / count, 4) if count else 0.0,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        calibration_band=band,
    )


def _summary(rows: list[FeedbackLearningRow], improvement_threshold: float) -> dict[str, Any]:
    enough = [row for row in rows if row.calibration_band != "insufficient_data"]
    error_rates = {
        row.bucket: round((row.false_positive_count + row.false_negative_count) / row.evaluated_count, 4)
        for row in enough
        if row.evaluated_count
    }
    trend = "insufficient_data"
    if len(enough) >= 2:
        first = error_rates[enough[0].bucket]
        latest = error_rates[enough[-1].bucket]
        if latest <= first - improvement_threshold:
            trend = "improving"
        elif latest >= first + improvement_threshold:
            trend = "degrading"
        else:
            trend = "stable"
    return {
        "bucket_count": len(rows),
        "evaluated_count": sum(row.evaluated_count for row in rows),
        "false_positive_count": sum(row.false_positive_count for row in rows),
        "false_negative_count": sum(row.false_negative_count for row in rows),
        "improving_bucket_count": sum(1 for row in enough if error_rates.get(row.bucket, 1.0) <= 0.1),
        "degrading_bucket_count": sum(1 for row in enough if error_rates.get(row.bucket, 0.0) > 0.35),
        "insufficient_data_bucket_count": sum(1 for row in rows if row.calibration_band == "insufficient_data"),
        "trend": trend,
    }


def _normalize_evaluation(item: FeedbackEvaluationRecord | Mapping[str, Any]) -> FeedbackEvaluationRecord:
    if isinstance(item, FeedbackEvaluationRecord):
        return item
    return FeedbackEvaluationRecord(
        unit_id=str(item.get("unit_id") or item.get("buildable_unit_id") or ""),
        recommendation=str(item.get("recommendation") or "maybe"),
        evaluated_at=item.get("evaluated_at") or item.get("created_at"),
    )


def _normalize_feedback(item: FeedbackOutcomeRecord | Mapping[str, Any]) -> FeedbackOutcomeRecord:
    if isinstance(item, FeedbackOutcomeRecord):
        return item
    return FeedbackOutcomeRecord(
        unit_id=str(item.get("unit_id") or item.get("buildable_unit_id") or ""),
        outcome=str(item.get("outcome") or ""),
        created_at=item.get("created_at") or item.get("reviewed_at"),
    )


def _bucket_key(value: datetime | str | date | None, bucket: str) -> str:
    dt = _coerce_datetime(value)
    return dt.strftime("%Y-%m-%d") if bucket == "day" else dt.strftime("%Y-%m")


def _coerce_datetime(value: datetime | str | date | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime(1970, 1, 1, tzinfo=UTC)


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(rows, key=lambda row: str(row.get("bucket") or ""))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
