"""Generate deterministic Markdown plans for change-freeze exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RISK_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
BLAST_RANK = {
    "enterprise": 5,
    "global": 5,
    "all customers": 5,
    "customer": 4,
    "production": 4,
    "prod": 4,
    "service": 3,
    "team": 2,
    "internal": 1,
    "local": 1,
}


@dataclass(frozen=True)
class FreezeExceptionRequest:
    request_id: str
    title: str
    status: str
    risk: str
    blast_radius: str
    owner: str
    approver: str
    expiry: str
    reason: str
    control: str
    rollback: str
    audit: str


def generate_change_freeze_exception_plan(spec_like: dict[str, Any] | None = None) -> str:
    """Return a stable Markdown plan for change-freeze exception handling."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    title = _title(spec, "Change Freeze Exception")
    requests = _requests(spec)
    lines = [
        f"# {title} Change Freeze Exception Plan",
        "",
        "## Summary",
        "",
        f"- Request count: {len(requests)}",
        f"- Highest risk: {_highest(requests, 'risk')}",
        f"- Broadest blast radius: {_highest(requests, 'blast_radius')}",
        "- Default owner: release_manager",
        "- Default approver: change_advisory_board",
        "- Default expiry: next freeze review",
        "",
        "## Request Inventory",
        "",
    ]
    for request in requests:
        lines.extend(
            [
                f"### {request.request_id}: {request.title}",
                "",
                f"- Status: {request.status}",
                f"- Risk: {request.risk}",
                f"- Blast radius: {request.blast_radius}",
                f"- Owner: {request.owner}",
                f"- Approver: {request.approver}",
                f"- Expiry: {request.expiry}",
                f"- Reason: {request.reason}",
                "",
            ]
        )
    lines.extend(["## Risk Controls", ""])
    for request in requests:
        lines.append(f"- {request.request_id}: {request.control}")
    lines.extend(["", "## Approval Path", ""])
    for request in requests:
        decision = "Reject or escalate before thaw" if request.status == "rejected" else "Approve before merge or deploy"
        lines.append(f"- {request.request_id}: {decision}; approver={request.approver}; owner={request.owner}.")
    lines.extend(["", "## Rollback Expectations", ""])
    for request in requests:
        lines.append(f"- {request.request_id}: {request.rollback}")
    lines.extend(["", "## Audit Trail", ""])
    for request in requests:
        lines.append(f"- {request.request_id}: {request.audit}")
    return "\n".join(lines).rstrip() + "\n"


def _requests(spec: dict[str, Any]) -> list[FreezeExceptionRequest]:
    raw_requests = _raw_requests(spec)
    if not raw_requests:
        raw_requests = [{"id": "CFE1", "title": "default freeze exception review"}]
    requests = [_request(index, item) for index, item in enumerate(raw_requests, start=1)]
    return sorted(
        requests,
        key=lambda item: (
            -RISK_RANK.get(item.risk, 0),
            -_blast_score(item.blast_radius),
            item.status != "rejected",
            item.expiry.casefold(),
            item.title.casefold(),
            item.request_id.casefold(),
        ),
    )


def _raw_requests(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    candidates = (
        _dict(metadata.get("change_freeze_exception_plan")).get("requests")
        or _dict(metadata.get("change_freeze_exception")).get("requests")
        or metadata.get("change_freeze_exceptions")
        or spec.get("change_freeze_exceptions")
        or spec.get("requests")
    )
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _request(index: int, item: dict[str, Any]) -> FreezeExceptionRequest:
    request_id = _text(item.get("id") or item.get("request_id")) or f"CFE{index}"
    title = _text(item.get("title") or item.get("name") or item.get("change")) or "unnamed freeze exception"
    status = _choice(item.get("status") or item.get("decision"), {"approved", "rejected", "pending"}, "pending")
    risk = _choice(item.get("risk") or item.get("risk_level") or item.get("severity"), set(RISK_RANK), "medium")
    blast_radius = _text(item.get("blast_radius") or item.get("impact") or item.get("scope")) or "service"
    owner = _text(item.get("owner") or item.get("request_owner")) or "release_manager"
    approver = _text(item.get("approver") or item.get("approval_owner")) or "change_advisory_board"
    expiry = _text(item.get("expiry") or item.get("expires_at") or item.get("review_by")) or "next freeze review"
    reason = _text(item.get("reason") or item.get("justification")) or "exception rationale must be attached before execution"
    control = _text(item.get("control") or item.get("risk_control")) or _default_control(risk, blast_radius)
    rollback = _text(item.get("rollback") or item.get("rollback_plan")) or "document rollback owner, trigger, and validation evidence before execution"
    audit = _text(item.get("audit") or item.get("audit_trail")) or "record requester, approver, decision, expiry, and post-change validation evidence"
    return FreezeExceptionRequest(
        request_id=request_id,
        title=title,
        status=status,
        risk=risk,
        blast_radius=blast_radius,
        owner=owner,
        approver=approver,
        expiry=expiry,
        reason=reason,
        control=control,
        rollback=rollback,
        audit=audit,
    )


def _default_control(risk: str, blast_radius: str) -> str:
    if risk in {"critical", "high"} or _blast_score(blast_radius) >= 4:
        return "require dual approval, pre-change validation, live monitoring, and rollback checkpoint"
    return "require owner review, scoped deployment, monitoring, and completion evidence"


def _highest(requests: list[FreezeExceptionRequest], field: str) -> str:
    if field == "risk":
        return max((item.risk for item in requests), key=lambda value: RISK_RANK.get(value, 0), default="medium")
    return max((item.blast_radius for item in requests), key=_blast_score, default="service")


def _blast_score(value: str) -> int:
    text = value.casefold()
    return max((score for term, score in BLAST_RANK.items() if term in text), default=2)


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
