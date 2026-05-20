"""Digest feedback outcomes into learning signals."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping


SCHEMA_VERSION = "max.feedback_outcome_learning_digest.v1"
KIND = "max.feedback_outcome_learning_digest"


def build_feedback_outcome_learning_digest(outcomes: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize approval, rejection, and shipped outcomes for scoring and source strategy."""

    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        key = (
            _clean(outcome.get("profile") or outcome.get("profile_id") or "unspecified"),
            _clean(outcome.get("category") or "uncategorized"),
            _clean(outcome.get("source") or outcome.get("source_id") or "unknown"),
            _clean(outcome.get("recommendation_status") or outcome.get("status") or "unknown"),
        )
        grouped[key].append(outcome)

    rows = [_learning_row(key, records) for key, records in grouped.items()]
    rows.sort(key=lambda row: (-float(row["confidence"]), _signal_order(row["recommended_learning"]), row["profile"], row["category"], row["source"], row["recommendation_status"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "outcome_count": len(outcomes),
            "group_count": len(rows),
            "positive_signal_count": sum(1 for row in rows if row["recommended_learning"].startswith("increase")),
            "negative_signal_count": sum(1 for row in rows if row["recommended_learning"].startswith("reduce")),
        },
        "learning_rows": rows,
    }


def render_feedback_outcome_learning_digest_markdown(digest: Mapping[str, Any]) -> str:
    """Render a feedback outcome learning digest as deterministic Markdown."""

    summary = digest["summary"]
    rows = list(digest.get("learning_rows", []))
    positives = [row for row in rows if row["recommended_learning"].startswith("increase")]
    negatives = [row for row in rows if row["recommended_learning"].startswith("reduce")]
    lines = [
        "# Feedback Outcome Learning Digest",
        "",
        f"Schema: `{digest['schema_version']}`",
        f"Outcomes analyzed: {summary['outcome_count']}",
        f"Groups analyzed: {summary['group_count']}",
        "",
        "## Strongest Positive Learning Signals",
        "",
    ]

    if positives:
        for row in positives[:5]:
            lines.append(f"- {row['profile']} / {row['category']} / {row['source']}: {row['recommended_learning']}")
    else:
        lines.append("- No positive learning signals detected.")

    lines.extend(["", "## Strongest Negative Learning Signals", ""])
    if negatives:
        for row in negatives[:5]:
            lines.append(f"- {row['profile']} / {row['category']} / {row['source']}: {row['recommended_learning']}")
    else:
        lines.append("- No negative learning signals detected.")

    lines.extend(["", "## Learning Detail", ""])
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['profile']} / {row['category']} / {row['source']} / {row['recommendation_status']}",
                    "",
                    f"- Approval rate: {row['approval_rate']:.3f}",
                    f"- Shipped rate: {row['shipped_rate']:.3f}",
                    f"- Rejection reason concentration: {row['rejection_reason_concentration']:.3f}",
                    f"- Confidence: {row['confidence']:.3f}",
                    f"- Recommended learning: {row['recommended_learning']}",
                    "",
                ]
            )
    else:
        lines.append("No feedback outcomes were provided.")

    return "\n".join(lines).rstrip() + "\n"


def _learning_row(key: tuple[str, str, str, str], records: list[Mapping[str, Any]]) -> dict[str, Any]:
    profile, category, source, recommendation_status = key
    total = len(records)
    approved = sum(1 for record in records if _outcome(record) in {"approved", "approval"})
    rejected = sum(1 for record in records if _outcome(record) in {"rejected", "rejection"})
    shipped = sum(1 for record in records if _truthy(record.get("shipped")) or _outcome(record) in {"shipped", "launched"})
    reasons = Counter(
        _clean(record.get("rejection_reason") or record.get("reason"))
        for record in records
        if _outcome(record) in {"rejected", "rejection"} and _clean(record.get("rejection_reason") or record.get("reason"))
    )
    top_reason_count = max(reasons.values(), default=0)
    approval_rate = approved / total if total else 0.0
    shipped_rate = shipped / total if total else 0.0
    concentration = top_reason_count / rejected if rejected else 0.0
    confidence = min(1.0, (total / 8.0) * 0.6 + abs(approval_rate - 0.5) * 0.25 + concentration * 0.15)

    return {
        "profile": profile,
        "category": category,
        "source": source,
        "recommendation_status": recommendation_status,
        "outcome_count": total,
        "approval_rate": round(approval_rate, 4),
        "shipped_rate": round(shipped_rate, 4),
        "rejection_reason_concentration": round(concentration, 4),
        "top_rejection_reason": reasons.most_common(1)[0][0] if reasons else None,
        "confidence": round(confidence, 4),
        "recommended_learning": _recommended_learning(approval_rate, shipped_rate, concentration, reasons.most_common(1)[0][0] if reasons else None),
    }


def _recommended_learning(
    approval_rate: float,
    shipped_rate: float,
    rejection_reason_concentration: float,
    top_reason: str | None,
) -> str:
    if approval_rate >= 0.7 and shipped_rate >= 0.4:
        return "increase scoring weight and preserve source strategy"
    if approval_rate <= 0.35 and rejection_reason_concentration >= 0.6:
        reason = top_reason or "repeated rejection reason"
        return f"reduce scoring weight; investigate {reason}"
    if shipped_rate >= 0.5:
        return "increase source follow-up for shipped recommendations"
    if approval_rate <= 0.4:
        return "reduce source weight until rejection patterns improve"
    return "hold scoring weight and continue collecting outcomes"


def _signal_order(learning: str) -> int:
    if learning.startswith("increase"):
        return 0
    if learning.startswith("reduce"):
        return 1
    return 2


def _outcome(record: Mapping[str, Any]) -> str:
    return _clean(record.get("outcome") or record.get("feedback_outcome") or record.get("decision")).lower()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "shipped", "launched"}
    return bool(value)


def _clean(value: Any) -> str:
    return str(value or "").strip()
