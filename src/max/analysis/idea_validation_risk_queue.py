"""Prioritized idea validation risk queue."""

from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "max.idea_validation_risk_queue.v1"
KIND = "max.idea_validation_risk_queue"


def build_idea_validation_risk_queue(ideas: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Convert idea validation signals into a deterministic prioritized risk queue."""

    rows = [_idea_row(idea, index) for index, idea in enumerate(ideas)]
    rows.sort(key=lambda row: (-float(row["risk_score"]), str(row["idea_id"])))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "idea_count": len(rows),
            "critical_count": sum(1 for row in rows if row["risk_tier"] == "critical"),
            "high_count": sum(1 for row in rows if row["risk_tier"] == "high"),
            "moderate_count": sum(1 for row in rows if row["risk_tier"] == "moderate"),
            "low_count": sum(1 for row in rows if row["risk_tier"] == "low"),
        },
        "risk_rows": rows,
    }


def render_idea_validation_risk_queue_markdown(queue: Mapping[str, Any]) -> str:
    """Render an idea validation risk queue as deterministic Markdown."""

    summary = queue["summary"]
    lines = [
        "# Idea Validation Risk Queue",
        "",
        f"Schema: `{queue['schema_version']}`",
        f"Ideas analyzed: {summary['idea_count']}",
        "",
        "## Tier Summary",
        "",
        f"- Critical: {summary['critical_count']}",
        f"- High: {summary['high_count']}",
        f"- Moderate: {summary['moderate_count']}",
        f"- Low: {summary['low_count']}",
        "",
        "## Prioritized Queue",
        "",
    ]

    rows = list(queue.get("risk_rows", []))
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['idea_id']}",
                    "",
                    f"- Risk tier: {row['risk_tier']}",
                    f"- Risk score: {row['risk_score']:.3f}",
                    f"- Top reasons: {', '.join(row['top_reasons'])}",
                    f"- Next validation action: {row['next_validation_action']}",
                    "",
                ]
            )
    else:
        lines.append("No idea validation signals were provided.")

    return "\n".join(lines).rstrip() + "\n"


def _idea_row(idea: Mapping[str, Any], index: int) -> dict[str, Any]:
    idea_id = _clean(idea.get("idea_id") or idea.get("id") or f"idea-{index + 1}")
    status = _clean(idea.get("validation_status") or idea.get("status") or "unknown").lower()
    blocker_count = _nonnegative_int(idea.get("blocker_count", idea.get("blockers", 0)))
    evidence_age_days = _nonnegative_int(idea.get("evidence_age_days", idea.get("evidence_age", 0)))
    customer_impact = _bounded_float(idea.get("customer_impact", idea.get("impact", 0.5)))
    confidence = _bounded_float(idea.get("confidence", 0.5))

    blocker_risk = min(1.0, blocker_count / 4.0)
    stale_risk = min(1.0, evidence_age_days / 90.0)
    confidence_risk = 1.0 - confidence
    status_risk = _status_risk(status)
    risk_score = round(
        (blocker_risk * 0.30)
        + (stale_risk * 0.25)
        + (confidence_risk * 0.20)
        + (customer_impact * 0.15)
        + (status_risk * 0.10),
        4,
    )
    tier = _risk_tier(risk_score)
    reasons = _top_reasons(blocker_count, evidence_age_days, confidence, customer_impact, status)

    return {
        "idea_id": idea_id,
        "validation_status": status,
        "blocker_count": blocker_count,
        "evidence_age_days": evidence_age_days,
        "customer_impact": customer_impact,
        "confidence": confidence,
        "risk_score": risk_score,
        "risk_tier": tier,
        "top_reasons": reasons,
        "next_validation_action": _next_action(tier, blocker_count, evidence_age_days, confidence, customer_impact),
    }


def _top_reasons(
    blocker_count: int,
    evidence_age_days: int,
    confidence: float,
    customer_impact: float,
    status: str,
) -> list[str]:
    scored = [
        (min(1.0, blocker_count / 4.0) * 0.30, f"{blocker_count} validation blocker(s)"),
        (min(1.0, evidence_age_days / 90.0) * 0.25, f"evidence age {evidence_age_days} day(s)"),
        ((1.0 - confidence) * 0.20, f"confidence {confidence:.2f}"),
        (customer_impact * 0.15, f"customer impact {customer_impact:.2f}"),
        (_status_risk(status) * 0.10, f"validation status {status}"),
    ]
    return [reason for score, reason in sorted(scored, key=lambda item: (-item[0], item[1]))[:3] if score > 0]


def _next_action(
    tier: str,
    blocker_count: int,
    evidence_age_days: int,
    confidence: float,
    customer_impact: float,
) -> str:
    if blocker_count > 0:
        return "resolve validation blockers before advancing the idea"
    if evidence_age_days >= 60:
        return "refresh stale evidence with current customer interviews"
    if confidence < 0.45 and customer_impact >= 0.65:
        return "run high-impact validation experiment to raise confidence"
    if tier in {"critical", "high"}:
        return "schedule focused validation review with explicit pass/fail criteria"
    return "keep monitoring validation signals on the normal cadence"


def _risk_tier(score: float) -> str:
    if score >= 0.70:
        return "critical"
    if score >= 0.50:
        return "high"
    if score >= 0.30:
        return "moderate"
    return "low"


def _status_risk(status: str) -> float:
    return {
        "blocked": 1.0,
        "invalidated": 0.9,
        "unknown": 0.7,
        "pending": 0.6,
        "mixed": 0.5,
        "in_review": 0.4,
        "validated": 0.0,
    }.get(status, 0.5)


def _bounded_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _nonnegative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, number)


def _clean(value: Any) -> str:
    return str(value or "").strip()
