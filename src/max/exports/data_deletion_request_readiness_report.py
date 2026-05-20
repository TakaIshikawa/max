"""Data deletion request readiness export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.data_deletion_request_readiness_report.v1"
KIND = "max.data_deletion_request_readiness_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"
DEFAULT_AS_OF = "2026-05-20"

SlaRisk = Literal["overdue", "due_soon", "on_track", "completed"]

_SLA_ORDER = {"overdue": 0, "due_soon": 1, "on_track": 2, "completed": 3}
_COMPLETE = {"complete", "completed", "closed", "done", "deleted"}
_VERIFIED = {"verified", "complete", "completed", "passed"}


class DataDeletionRequestReadinessInput(TypedDict, total=False):
    request_id: str
    id: str
    customer: str
    account: str
    region: str
    request_type: str
    type: str
    status: str
    submitted_at: str
    due_at: str
    system: str
    deletion_owner: str
    owner: str
    verification_status: str
    exception_reason: str
    blocker: bool | str


def build_data_deletion_request_readiness_report(
    records: Iterable[DataDeletionRequestReadinessInput | dict[str, Any]],
    *,
    as_of: str = DEFAULT_AS_OF,
    title: str = "Data Deletion Request Readiness Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    due_soon_days: int = 3,
) -> dict[str, Any]:
    rows = _normalize_records(records, as_of=as_of, due_soon_days=due_soon_days)
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "as_of": as_of,
        "title": _text(title) or "Data Deletion Request Readiness Report",
        "summary": summary,
        "request_rows": rows,
        "system_breakdown": _system_breakdown(rows),
        "sla_risk_requests": _sla_risk_requests(rows),
        "verification_gaps": _verification_gaps(rows),
        "exception_queue": _exception_queue(rows),
        "recommended_actions": _recommended_actions(summary, rows),
    }


def render_data_deletion_request_readiness_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Data Deletion Request Readiness Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        f"Generated: {report.get('generated_at', DEFAULT_GENERATED_AT)}",
        f"As of: {report.get('as_of') or DEFAULT_AS_OF}",
        "",
        "## Summary",
        "",
        f"- Requests: {summary.get('request_count', 0)}",
        f"- Open requests: {summary.get('open_request_count', 0)}",
        f"- SLA risk requests: {summary.get('sla_risk_count', 0)}",
        f"- Verification gaps: {summary.get('verification_gap_count', 0)}",
        f"- Exceptions: {summary.get('exception_count', 0)}",
        "",
        "## Requests",
        "",
    ]
    if report.get("request_rows"):
        lines.extend(["| Request | Customer | System | Status | SLA Risk | Days Open | Due In | Owner |", "|---------|----------|--------|--------|----------|-----------|--------|-------|"])
        for row in report["request_rows"]:
            lines.append(
                f"| {_md(row['request_id'])} | {_md(row['customer'])} | {_md(row['system'])} | {_md(row['status'])} | "
                f"{row['sla_risk']} | {row['days_open']} | {row['days_until_due']} | {_md(row['deletion_owner'])} |"
            )
    else:
        lines.append("- No data deletion requests were supplied.")

    lines.extend(["", "## SLA Risk Requests", ""])
    if report.get("sla_risk_requests"):
        for row in report["sla_risk_requests"]:
            lines.append(f"- {row['request_id']}: {row['sla_risk']} for {row['customer']} in {row['system']}")
    else:
        lines.append("- No open requests are at SLA risk.")
    return "\n".join(lines).rstrip() + "\n"


def render_data_deletion_request_readiness_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[DataDeletionRequestReadinessInput | dict[str, Any]], *, as_of: str, due_soon_days: int) -> list[dict[str, Any]]:
    as_of_date = _parse_date(as_of)
    rows = []
    for index, raw in enumerate(records):
        status = _status(raw.get("status"))
        verification = _text(raw.get("verification_status") or "unknown").lower().replace("_", " ")
        submitted_at = _text(raw.get("submitted_at"))
        due_at = _text(raw.get("due_at"))
        submitted = _parse_date(submitted_at)
        due = _parse_date(due_at)
        completed = _is_completed(status)
        verified = _is_verified(verification)
        days_open = (as_of_date - submitted).days if submitted else 0
        days_until_due = (due - as_of_date).days if due else None
        blocker = _bool(raw.get("blocker"))
        exception_reason = _text(raw.get("exception_reason"))
        rows.append(
            {
                "request_id": _text(raw.get("request_id") or raw.get("id") or f"request-{index + 1}"),
                "customer": _text(raw.get("customer") or raw.get("account") or "Unknown customer"),
                "region": _text(raw.get("region") or "Unspecified region"),
                "request_type": _text(raw.get("request_type") or raw.get("type") or "deletion"),
                "status": status,
                "submitted_at": submitted_at,
                "due_at": due_at,
                "system": _text(raw.get("system") or "Unspecified system"),
                "deletion_owner": _text(raw.get("deletion_owner") or raw.get("owner") or "Unassigned"),
                "verification_status": verification,
                "exception_reason": exception_reason,
                "blocker": blocker,
                "days_open": max(days_open, 0),
                "days_until_due": days_until_due,
                "completed": completed,
                "verified": verified,
                "sla_risk": _sla_risk(completed=completed, due=due, as_of_date=as_of_date, due_soon_days=due_soon_days, blocker=blocker),
                "_input_order": index,
            }
        )
    rows.sort(key=lambda row: (_SLA_ORDER[row["sla_risk"]], row["days_until_due"] if row["days_until_due"] is not None else 9999, row["system"].lower(), row["request_id"].lower(), row["_input_order"]))
    for row in rows:
        row.pop("_input_order", None)
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_rows = [row for row in rows if not row["completed"]]
    return {
        "request_count": len(rows),
        "open_request_count": len(open_rows),
        "completed_verified_count": sum(1 for row in rows if row["completed"] and row["verified"]),
        "sla_risk_count": sum(1 for row in open_rows if row["sla_risk"] in {"overdue", "due_soon"}),
        "verification_gap_count": len(_verification_gaps(rows)),
        "exception_count": len(_exception_queue(rows)),
        "unassigned_owner_count": sum(1 for row in open_rows if row["deletion_owner"] == "Unassigned"),
    }


def _system_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["system"]].append(row)
    output = []
    for system, items in grouped.items():
        risks = Counter(row["sla_risk"] for row in items)
        output.append(
            {
                "system": system,
                "request_count": len(items),
                "open_request_count": sum(1 for row in items if not row["completed"]),
                "sla_risk_counts": {risk: risks.get(risk, 0) for risk in ("overdue", "due_soon", "on_track", "completed")},
                "verification_gap_count": len(_verification_gaps(items)),
                "exception_count": len(_exception_queue(items)),
            }
        )
    output.sort(key=lambda row: (-(row["sla_risk_counts"]["overdue"] + row["sla_risk_counts"]["due_soon"]), -row["verification_gap_count"], row["system"].lower()))
    return output


def _sla_risk_requests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = [
        {
            "request_id": row["request_id"],
            "customer": row["customer"],
            "system": row["system"],
            "status": row["status"],
            "sla_risk": row["sla_risk"],
            "days_until_due": row["days_until_due"],
            "deletion_owner": row["deletion_owner"],
            "blocker": row["blocker"],
        }
        for row in rows
        if not row["completed"] and row["sla_risk"] in {"overdue", "due_soon"}
    ]
    output.sort(key=lambda row: (_SLA_ORDER[row["sla_risk"]], row["days_until_due"] if row["days_until_due"] is not None else 9999, row["request_id"].lower()))
    return output


def _verification_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = [
        {
            "request_id": row["request_id"],
            "customer": row["customer"],
            "system": row["system"],
            "status": row["status"],
            "verification_status": row["verification_status"],
            "deletion_owner": row["deletion_owner"],
        }
        for row in rows
        if not row["completed"] and not row["verified"]
    ]
    output.sort(key=lambda row: (row["system"].lower(), row["request_id"].lower()))
    return output


def _exception_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = [
        {
            "request_id": row["request_id"],
            "customer": row["customer"],
            "system": row["system"],
            "exception_reason": row["exception_reason"],
            "blocker": row["blocker"],
            "deletion_owner": row["deletion_owner"],
        }
        for row in rows
        if not row["completed"] and (row["exception_reason"] or row["blocker"])
    ]
    output.sort(key=lambda row: (not row["blocker"], row["system"].lower(), row["request_id"].lower()))
    return output


def _recommended_actions(summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    actions = []
    if summary.get("sla_risk_count", 0):
        actions.append(f"Prioritize {summary['sla_risk_count']} open deletion request(s) at SLA risk.")
    if summary.get("verification_gap_count", 0):
        actions.append(f"Resolve verification gaps for {summary['verification_gap_count']} open request(s).")
    if summary.get("unassigned_owner_count", 0):
        actions.append(f"Assign deletion owners for {summary['unassigned_owner_count']} open request(s).")
    if rows and not actions:
        actions.append("Continue monitoring deletion readiness through completion and verification.")
    return actions


def _sla_risk(*, completed: bool, due: date | None, as_of_date: date, due_soon_days: int, blocker: bool) -> SlaRisk:
    if completed:
        return "completed"
    if blocker:
        return "overdue"
    if due is None:
        return "on_track"
    days = (due - as_of_date).days
    if days < 0:
        return "overdue"
    if days <= due_soon_days:
        return "due_soon"
    return "on_track"


def _status(value: Any) -> str:
    return _text(value).lower().replace("_", " ") or "unknown"


def _is_completed(status: str) -> bool:
    return status in _COMPLETE


def _is_verified(status: str) -> bool:
    return status in _VERIFIED


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    return text in {"1", "true", "yes", "y", "blocked", "blocker"}


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
