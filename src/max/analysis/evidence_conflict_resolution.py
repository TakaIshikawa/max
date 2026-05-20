"""Deterministic evidence conflict resolution analysis."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Mapping


SCHEMA_VERSION = "max.evidence_conflict_resolution.v1"
KIND = "max.evidence_conflict_resolution"

_POSITIVE = {
    "positive",
    "support",
    "supports",
    "supporting",
    "supported",
    "confirm",
    "confirms",
    "confirmed",
    "validate",
    "validates",
    "validated",
    "yes",
    "true",
    "pro",
}
_NEGATIVE = {
    "negative",
    "oppose",
    "opposes",
    "opposing",
    "contradict",
    "contradicts",
    "contradicting",
    "refute",
    "refutes",
    "refuting",
    "invalidate",
    "invalidates",
    "invalidated",
    "no",
    "false",
    "con",
}
_NEUTRAL = {"neutral", "mixed", "unclear", "unknown", "inconclusive"}


def build_evidence_conflict_resolution_analysis(claims: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Group evidence claims by topic and recommend deterministic resolution actions."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    topic_labels: dict[str, str] = {}
    for index, claim in enumerate(claims):
        record = _claim_record(claim, index)
        grouped[record["normalized_topic"]].append(record)
        topic_labels.setdefault(record["normalized_topic"], record["topic"])

    rows = [
        _resolution_row(topic_key, topic_labels[topic_key], grouped[topic_key])
        for topic_key in sorted(grouped)
    ]
    rows.sort(
        key=lambda row: (
            0 if row["conflict_status"] == "conflict" else 1,
            -row["resolution_priority"],
            -row["strongest_score"],
            row["normalized_topic"],
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "claim_count": len(claims),
            "topic_count": len(rows),
            "conflict_count": sum(1 for row in rows if row["conflict_status"] == "conflict"),
            "non_conflict_count": sum(1 for row in rows if row["conflict_status"] != "conflict"),
        },
        "resolution_rows": rows,
    }


def render_evidence_conflict_resolution_markdown(report: Mapping[str, Any]) -> str:
    """Render an evidence conflict resolution analysis as deterministic Markdown."""

    summary = report["summary"]
    lines = [
        "# Evidence Conflict Resolution Analysis",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Claims analyzed: {summary['claim_count']}",
        f"Topics analyzed: {summary['topic_count']}",
        f"Conflicts detected: {summary['conflict_count']}",
        "",
        "## Resolution Queue",
        "",
    ]

    rows = list(report.get("resolution_rows", []))
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['topic']}",
                    "",
                    f"- Status: {row['conflict_status']}",
                    f"- Strongest supporting source: {row['strongest_supporting_source'] or 'None'}",
                    f"- Strongest opposing source: {row['strongest_opposing_source'] or 'None'}",
                    f"- Confidence gap: {row['confidence_gap']:.3f}",
                    f"- Recommended action: {row['recommended_action']}",
                    "",
                ]
            )
    else:
        lines.append("No evidence claims were provided.")

    lines.extend(["## Topic Details", ""])
    for row in rows:
        lines.append(
            f"- {row['topic']}: {row['positive_count']} positive, "
            f"{row['negative_count']} negative, {row['neutral_count']} neutral claim(s)."
        )

    return "\n".join(lines).rstrip() + "\n"


def normalize_topic(value: Any) -> str:
    """Normalize a topic for deterministic grouping."""

    text = str(value or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"([a-z])([0-9])", r"\1 \2", text)
    text = re.sub(r"([0-9])([a-z])", r"\1 \2", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip() or "unspecified"


def _claim_record(claim: Mapping[str, Any], index: int) -> dict[str, Any]:
    topic = _clean(claim.get("topic") or claim.get("subject") or claim.get("claim") or "unspecified")
    polarity = _polarity(claim.get("polarity") or claim.get("stance") or claim.get("sentiment"))
    observed_at = _observed_at(claim.get("observed_at") or claim.get("date") or claim.get("created_at"))
    reliability = _bounded_float(claim.get("reliability", claim.get("confidence", 0.5)))
    recency_score = _recency_score(observed_at)
    score = round((reliability * 0.75) + (recency_score * 0.25), 4)
    source = _clean(claim.get("source") or claim.get("source_id") or claim.get("source_adapter") or f"claim-{index + 1}")

    return {
        "id": _clean(claim.get("id") or f"ECR-C{index + 1:03d}"),
        "topic": topic,
        "normalized_topic": normalize_topic(topic),
        "claim": _clean(claim.get("claim") or claim.get("text") or topic),
        "source": source,
        "polarity": polarity,
        "reliability": reliability,
        "observed_at": observed_at,
        "recency_score": recency_score,
        "score": score,
    }


def _resolution_row(topic_key: str, topic_label: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [record for record in records if record["polarity"] == "positive"]
    negatives = [record for record in records if record["polarity"] == "negative"]
    neutrals = [record for record in records if record["polarity"] == "neutral"]
    strongest_support = _strongest(positives)
    strongest_oppose = _strongest(negatives)
    support_score = float(strongest_support["score"]) if strongest_support else 0.0
    oppose_score = float(strongest_oppose["score"]) if strongest_oppose else 0.0
    confidence_gap = round(abs(support_score - oppose_score), 3)
    conflict = bool(positives and negatives)

    return {
        "topic": topic_label,
        "normalized_topic": topic_key,
        "conflict_status": "conflict" if conflict else "no_conflict",
        "positive_count": len(positives),
        "negative_count": len(negatives),
        "neutral_count": len(neutrals),
        "claim_count": len(records),
        "strongest_supporting_source": strongest_support["source"] if strongest_support else None,
        "strongest_opposing_source": strongest_oppose["source"] if strongest_oppose else None,
        "confidence_gap": confidence_gap,
        "resolution_priority": _resolution_priority(conflict, confidence_gap, records),
        "strongest_score": max([float(record["score"]) for record in records], default=0.0),
        "recommended_action": _recommended_action(conflict, support_score, oppose_score, confidence_gap, neutrals),
        "claims": sorted(records, key=_detail_record_sort_key),
    }


def _strongest(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return sorted(records, key=_record_sort_key)[0]


def _record_sort_key(record: Mapping[str, Any]) -> tuple[float, str, str, str]:
    return (
        -float(record["score"]),
        str(record.get("observed_at") or ""),
        str(record["source"]),
        str(record["id"]),
    )


def _detail_record_sort_key(record: Mapping[str, Any]) -> tuple[int, float, str, str, str]:
    polarity_order = {"positive": 0, "negative": 1, "neutral": 2}
    return (
        polarity_order.get(str(record["polarity"]), 3),
        -float(record["score"]),
        str(record.get("observed_at") or ""),
        str(record["source"]),
        str(record["id"]),
    )


def _resolution_priority(conflict: bool, confidence_gap: float, records: list[dict[str, Any]]) -> float:
    polarity_count = len({record["polarity"] for record in records})
    strongest = max([float(record["score"]) for record in records], default=0.0)
    priority = strongest + (0.25 if conflict else 0.0) + (0.1 if polarity_count > 1 else 0.0) - min(confidence_gap, 1.0) * 0.1
    return round(priority, 4)


def _recommended_action(
    conflict: bool,
    support_score: float,
    oppose_score: float,
    confidence_gap: float,
    neutrals: list[dict[str, Any]],
) -> str:
    if conflict and confidence_gap < 0.05:
        return "manual review: reconcile equally credible contradictory evidence"
    if conflict and support_score > oppose_score:
        return "prefer supporting claim; verify opposing source freshness before closing"
    if conflict:
        return "prefer opposing claim; verify supporting source freshness before closing"
    if neutrals and not support_score and not oppose_score:
        return "collect directional evidence before making a decision"
    return "no conflict detected; monitor for new contradictory evidence"


def _polarity(value: Any) -> str:
    normalized = normalize_topic(value).replace(" ", "_")
    if normalized in _POSITIVE:
        return "positive"
    if normalized in _NEGATIVE:
        return "negative"
    if normalized in _NEUTRAL:
        return "neutral"
    return "neutral"


def _observed_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _clean(value)
    if not text:
        return ""
    return text[:10]


def _recency_score(observed_at: str) -> float:
    if not observed_at:
        return 0.0
    try:
        observed = date.fromisoformat(observed_at)
    except ValueError:
        return 0.0
    ordinal = observed.toordinal()
    return round(max(0.0, min(1.0, (ordinal - date(2020, 1, 1).toordinal()) / 3650)), 4)


def _bounded_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.5
    return round(max(0.0, min(1.0, number)), 4)


def _clean(value: Any) -> str:
    return str(value or "").strip()
