"""Generate deterministic Markdown plans for access review campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RISK_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass(frozen=True)
class ReviewAssignment:
    system: str
    reviewer: str
    population: tuple[str, ...]
    due_date: str
    risk: str
    status: str
    escalation_tiers: tuple[str, ...]
    remediation_actions: tuple[str, ...]
    evidence: str


def generate_access_review_campaign_plan(spec_like: dict[str, Any] | None = None) -> str:
    """Return a stable Markdown plan for an access review campaign."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    title = _title(spec, "Access Review Campaign")
    assignments = _assignments(spec)
    lines = [
        f"# {title} Access Review Campaign Plan",
        "",
        "## Campaign Summary",
        "",
        f"- System count: {len({item.system for item in assignments})}",
        f"- Reviewer count: {len({item.reviewer for item in assignments})}",
        f"- Overdue assignments: {sum(1 for item in assignments if item.status == 'overdue')}",
        f"- Highest risk: {_highest_risk(assignments)}",
        "- Default reviewer: access_review_owner",
        "- Default due date: next campaign checkpoint",
        "",
        "## Review Scope",
        "",
    ]
    for item in assignments:
        lines.extend(
            [
                f"### {item.system}",
                "",
                f"- Reviewer: {item.reviewer}",
                f"- Population: {', '.join(item.population)}",
                f"- Due date: {item.due_date}",
                f"- Risk: {item.risk}",
                f"- Status: {item.status}",
                "",
            ]
        )
    lines.extend(["## Reviewer Assignments", ""])
    for item in assignments:
        lines.append(f"- {item.reviewer}: review {item.system} for {', '.join(item.population)} by {item.due_date}.")
    lines.extend(["", "## Escalation Schedule", ""])
    for item in assignments:
        lines.append(f"- {item.system}: {' > '.join(item.escalation_tiers)}.")
    lines.extend(["", "## Remediation Queue", ""])
    for item in assignments:
        for action in item.remediation_actions:
            lines.append(f"- {item.system}: {action}")
    lines.extend(["", "## Evidence Capture", ""])
    for item in assignments:
        lines.append(f"- {item.system}: {item.evidence}")
    return "\n".join(lines).rstrip() + "\n"


def _assignments(spec: dict[str, Any]) -> list[ReviewAssignment]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(_raw_reviews(spec), start=1):
        system = _text(raw.get("system") or raw.get("name") or raw.get("application")) or f"system-{index}"
        reviewer = _text(raw.get("reviewer") or raw.get("owner") or raw.get("manager")) or "access_review_owner"
        key = (system.casefold(), reviewer.casefold())
        existing = grouped.setdefault(
            key,
            {
                "system": system,
                "reviewer": reviewer,
                "population": [],
                "due_date": "",
                "risk": "low",
                "status": "on-track",
                "escalation_tiers": [],
                "remediation_actions": [],
                "evidence": "",
            },
        )
        existing["population"].extend(_values(raw.get("population") or raw.get("populations") or raw.get("users"), ["all active users"]))
        existing["due_date"] = _earliest(existing["due_date"], _text(raw.get("due_date") or raw.get("due") or raw.get("deadline")) or "next campaign checkpoint")
        risk = _choice(raw.get("risk") or raw.get("risk_level"), set(RISK_RANK), "medium")
        existing["risk"] = max((existing["risk"], risk), key=lambda value: RISK_RANK.get(value, 0))
        status = _status(raw)
        if status == "overdue" or existing["status"] != "overdue":
            existing["status"] = status
        existing["escalation_tiers"].extend(
            _values(raw.get("escalation_tiers") or raw.get("escalations"), _default_escalations(status, risk))
        )
        existing["remediation_actions"].extend(
            _values(raw.get("remediation_actions") or raw.get("remediation"), _default_remediation(status, risk))
        )
        existing["evidence"] = _text(raw.get("evidence") or raw.get("evidence_capture")) or existing["evidence"] or "capture reviewer decision, export timestamp, removals, and exception expiry"
    if not grouped:
        grouped[("primary system", "access_review_owner")] = {
            "system": "primary system",
            "reviewer": "access_review_owner",
            "population": ["all active users"],
            "due_date": "next campaign checkpoint",
            "risk": "medium",
            "status": "on-track",
            "escalation_tiers": ["reviewer", "system_owner", "security_owner"],
            "remediation_actions": ["remove stale access and document retained exceptions"],
            "evidence": "capture reviewer decision, export timestamp, removals, and exception expiry",
        }
    assignments = [
        ReviewAssignment(
            system=item["system"],
            reviewer=item["reviewer"],
            population=tuple(_unique(item["population"])),
            due_date=item["due_date"],
            risk=item["risk"],
            status=item["status"],
            escalation_tiers=tuple(_dedupe(item["escalation_tiers"])),
            remediation_actions=tuple(_dedupe(item["remediation_actions"])),
            evidence=item["evidence"],
        )
        for item in grouped.values()
    ]
    return sorted(
        assignments,
        key=lambda item: (
            item.status != "overdue",
            -RISK_RANK.get(item.risk, 0),
            item.due_date.casefold(),
            item.system.casefold(),
            item.reviewer.casefold(),
        ),
    )


def _raw_reviews(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    campaign = _dict(metadata.get("access_review_campaign") or spec.get("access_review_campaign"))
    candidates = campaign.get("systems") or campaign.get("reviews") or metadata.get("access_reviews") or spec.get("reviews")
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _status(raw: dict[str, Any]) -> str:
    status = _choice(raw.get("status"), {"overdue", "on-track", "blocked", "complete"}, "")
    if status:
        return status
    if raw.get("overdue") is True or _text(raw.get("overdue")).casefold() in {"true", "yes", "1"}:
        return "overdue"
    return "on-track"


def _default_escalations(status: str, risk: str) -> list[str]:
    if status == "overdue" or risk in {"critical", "high"}:
        return ["reviewer", "system_owner", "security_owner", "executive_sponsor"]
    return ["reviewer", "system_owner", "security_owner"]


def _default_remediation(status: str, risk: str) -> list[str]:
    if status == "overdue" or risk in {"critical", "high"}:
        return ["disable unreviewed privileged access", "open dated exception for retained access"]
    return ["remove stale access and document retained exceptions"]


def _highest_risk(assignments: list[ReviewAssignment]) -> str:
    return max((item.risk for item in assignments), key=lambda value: RISK_RANK.get(value, 0), default="medium")


def _earliest(left: str, right: str) -> str:
    if not left:
        return right
    if right == "next campaign checkpoint":
        return left
    if left == "next campaign checkpoint":
        return right
    return min(left, right)


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _unique(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _title(spec: dict[str, Any], fallback: str) -> str:
    project = _dict(spec.get("project"))
    source = _dict(spec.get("source"))
    return _text(project.get("title") or spec.get("title") or source.get("idea_id")) or fallback


def _choice(value: Any, allowed: set[str], fallback: str) -> str:
    text = _text(value).casefold()
    return text if text in allowed else fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
