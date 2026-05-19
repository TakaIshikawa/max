"""Generate deterministic Markdown plans for operational-readiness waivers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass(frozen=True)
class ReadinessWaiver:
    waiver_id: str
    reason: str
    severity: str
    status: str
    owner: str
    approver: str
    expiry: str
    review_cadence: str
    unmet_criteria: tuple[str, ...]
    compensating_controls: tuple[str, ...]
    follow_up_actions: tuple[str, ...]


def generate_operational_readiness_waiver_plan(spec_like: dict[str, Any] | None = None) -> str:
    """Return a stable Markdown plan for operational-readiness waivers."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    title = _title(spec, "Operational Readiness Waiver")
    waivers = _waivers(spec)
    lines = [
        f"# {title} Operational Readiness Waiver Plan",
        "",
        "## Waiver Summary",
        "",
        f"- Waiver count: {len(waivers)}",
        f"- Expired waivers: {sum(1 for item in waivers if item.status == 'expired')}",
        f"- Highest severity: {_highest_severity(waivers)}",
        "- Default owner: readiness_owner",
        "- Default expiry: next readiness review",
        "- Default compensating control: daily readiness owner review with documented go/no-go decision",
        "",
    ]
    lines.extend(["## Unmet Criteria", ""])
    for waiver in waivers:
        lines.extend([f"### {waiver.waiver_id}", ""])
        lines.append(f"- Reason: {waiver.reason}")
        lines.append(f"- Severity: {waiver.severity}")
        lines.append(f"- Status: {waiver.status}")
        lines.append(f"- Owner: {waiver.owner}")
        for criterion in waiver.unmet_criteria:
            lines.append(f"- Criterion: {criterion}")
        lines.append("")
    lines.extend(["## Compensating Controls", ""])
    for waiver in waivers:
        for control in waiver.compensating_controls:
            lines.append(f"- {waiver.waiver_id}: {control}")
    lines.extend(["", "## Approval Requirements", ""])
    for waiver in waivers:
        lines.append(f"- {waiver.waiver_id}: approver={waiver.approver}; owner={waiver.owner}; severity={waiver.severity}.")
    lines.extend(["", "## Expiry Review", ""])
    for waiver in waivers:
        escalation = "escalate immediately and block expansion" if waiver.status == "expired" else "review before expiry or renewal"
        lines.append(f"- {waiver.waiver_id}: expiry={waiver.expiry}; cadence={waiver.review_cadence}; action={escalation}.")
    lines.extend(["", "## Closure Checklist", ""])
    for waiver in waivers:
        for action in waiver.follow_up_actions:
            lines.append(f"- {waiver.waiver_id}: {action}")
    return "\n".join(lines).rstrip() + "\n"


def _waivers(spec: dict[str, Any]) -> list[ReadinessWaiver]:
    raw_waivers = _raw_waivers(spec)
    if not raw_waivers:
        raw_waivers = [{"id": "ORW1", "reason": "readiness waiver requires owner review"}]
    waivers = [_waiver(index, item) for index, item in enumerate(raw_waivers, start=1)]
    return sorted(
        waivers,
        key=lambda item: (
            item.status != "expired",
            -SEVERITY_RANK.get(item.severity, 0),
            item.expiry.casefold(),
            item.waiver_id.casefold(),
            item.reason.casefold(),
        ),
    )


def _raw_waivers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    candidates = (
        _dict(metadata.get("operational_readiness_waiver")).get("waivers")
        or _dict(metadata.get("operational_readiness_waiver_plan")).get("waivers")
        or metadata.get("operational_readiness_waivers")
        or spec.get("operational_readiness_waivers")
        or spec.get("waivers")
    )
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _waiver(index: int, item: dict[str, Any]) -> ReadinessWaiver:
    waiver_id = _text(item.get("id") or item.get("waiver_id")) or f"ORW{index}"
    severity = _choice(item.get("severity") or item.get("risk"), set(SEVERITY_RANK), "medium")
    status = _status(item)
    owner = _text(item.get("owner") or item.get("readiness_owner")) or "readiness_owner"
    approver = _text(item.get("approver") or item.get("approval_owner")) or _default_approver(severity, status)
    expiry = _text(item.get("expiry") or item.get("expires_at") or item.get("review_by")) or "next readiness review"
    reason = _text(item.get("reason") or item.get("waiver_reason")) or "temporary waiver for unmet operational readiness criteria"
    unmet_criteria = tuple(_unique(_values(item.get("unmet_criteria") or item.get("criteria"), ["readiness criterion pending validation"])))
    compensating_controls = tuple(
        _unique(
            _values(
                item.get("compensating_controls") or item.get("controls"),
                ["daily readiness owner review with documented go/no-go decision"],
            )
        )
    )
    follow_up_actions = tuple(
        _unique(
            _values(
                item.get("follow_up_actions") or item.get("actions"),
                ["close unmet criteria", "attach validation evidence", "record waiver closure decision"],
            )
        )
    )
    review_cadence = _text(item.get("review_cadence") or item.get("cadence")) or _default_cadence(severity, status)
    return ReadinessWaiver(
        waiver_id=waiver_id,
        reason=reason,
        severity=severity,
        status=status,
        owner=owner,
        approver=approver,
        expiry=expiry,
        review_cadence=review_cadence,
        unmet_criteria=unmet_criteria,
        compensating_controls=compensating_controls,
        follow_up_actions=follow_up_actions,
    )


def _status(item: dict[str, Any]) -> str:
    status = _choice(item.get("status"), {"active", "expired", "pending", "closed"}, "")
    if status:
        return status
    if item.get("expired") is True or _text(item.get("expired")).casefold() in {"true", "yes", "1"}:
        return "expired"
    if "expired" in _text(item.get("expiry")).casefold():
        return "expired"
    return "active"


def _default_approver(severity: str, status: str) -> str:
    if status == "expired" or severity in {"critical", "high"}:
        return "executive_sponsor"
    return "readiness_approver"


def _default_cadence(severity: str, status: str) -> str:
    if status == "expired" or severity in {"critical", "high"}:
        return "daily until closed"
    return "weekly until closed"


def _highest_severity(waivers: list[ReadinessWaiver]) -> str:
    return max((item.severity for item in waivers), key=lambda value: SEVERITY_RANK.get(value, 0), default="medium")


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _unique(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)


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
