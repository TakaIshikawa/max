"""Data access audit finding summary export."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.data_access_audit_summary.v1"
KIND = "max.data_access_audit_summary"

FindingType = Literal["excessive_privileges", "stale_access", "privileged_account", "unresolved_exception", "other"]
FindingStatus = Literal["open", "exception", "remediated"]
RiskLevel = Literal["critical", "high", "medium", "low", "unknown"]
GroupBy = Literal["system", "dataset", "principal", "owner"]


class DataAccessAuditFindingInput(TypedDict, total=False):
    system: str
    dataset: str
    principal: str
    owner: str
    finding_type: str
    finding: str
    risk: str
    risk_level: str
    status: str
    remediation: str
    recommended_remediation: str
    evidence_links: str | list[str]
    evidence: str | list[str]
    last_seen: str


def build_data_access_audit_summary_report(
    records: Iterable[DataAccessAuditFindingInput | dict[str, Any]],
    *,
    title: str = "Data Access Audit Summary",
    group_by: GroupBy = "system",
) -> dict[str, Any]:
    findings = _normalize_findings(records)
    groups = _groups(findings, group_by)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Data Access Audit Summary",
        "group_by": group_by,
        "summary": _summary(findings, groups),
        "groups": groups,
        "findings": findings,
    }


def render_data_access_audit_summary_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Data Access Audit Summary'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Findings: {summary.get('finding_count', 0)}",
        f"- Open findings: {summary.get('open_count', 0)}",
        f"- Critical/high risk: {summary.get('critical_high_count', 0)}",
        f"- Excessive privileges: {summary.get('excessive_privileges_count', 0)}",
        f"- Stale access: {summary.get('stale_access_count', 0)}",
        f"- Privileged accounts: {summary.get('privileged_account_count', 0)}",
        f"- Unresolved exceptions: {summary.get('unresolved_exception_count', 0)}",
        "",
        "## Finding Register",
        "",
    ]
    groups = report.get("groups") or []
    if groups:
        for group in groups:
            lines.extend([f"### {group['name']}", ""])
            for finding in group["findings"]:
                evidence = ", ".join(finding["evidence_links"]) or "None supplied"
                lines.extend(
                    [
                        f"#### {finding['system']} - {finding['dataset']} - {finding['principal']}",
                        f"- Owner: {finding['owner']}",
                        f"- Finding type: {finding['finding_type']}",
                        f"- Risk: {finding['risk_level']}",
                        f"- Status: {finding['status']}",
                        f"- Last seen: {finding['last_seen'] or 'Not supplied'}",
                        f"- Recommended remediation: {finding['recommended_remediation']}",
                        f"- Evidence links: {evidence}",
                        "",
                    ]
                )
    else:
        lines.append("- No data access audit findings were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_data_access_audit_summary_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_findings(records: Iterable[DataAccessAuditFindingInput | dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for raw in records:
        finding_type = _finding_type(raw.get("finding_type") or raw.get("finding"))
        findings.append(
            {
                "system": _text(raw.get("system") or "Unspecified system"),
                "dataset": _text(raw.get("dataset") or "Unspecified dataset"),
                "principal": _text(raw.get("principal") or "Unspecified principal"),
                "owner": _text(raw.get("owner") or "Unassigned"),
                "finding_type": finding_type,
                "risk_level": _risk(raw.get("risk_level") or raw.get("risk"), finding_type=finding_type),
                "status": _status(raw.get("status"), finding_type=finding_type),
                "last_seen": _text(raw.get("last_seen")),
                "recommended_remediation": _text(raw.get("recommended_remediation") or raw.get("remediation") or _recommended_remediation(finding_type)),
                "evidence_links": _items(raw.get("evidence_links") or raw.get("evidence")),
            }
        )
    findings.sort(key=_finding_sort_key)
    return findings


def _groups(findings: list[dict[str, Any]], group_by: GroupBy) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[finding[group_by]].append(finding)
    groups = [{"name": name, "finding_count": len(rows), "findings": rows} for name, rows in grouped.items()]
    groups.sort(key=lambda group: (_group_worst_key(group["findings"]), group["name"].lower()))
    return groups


def _summary(findings: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "finding_count": len(findings),
        "group_count": len(groups),
        "open_count": sum(1 for finding in findings if finding["status"] != "remediated"),
        "critical_high_count": sum(1 for finding in findings if finding["risk_level"] in {"critical", "high"}),
        "excessive_privileges_count": sum(1 for finding in findings if finding["finding_type"] == "excessive_privileges"),
        "stale_access_count": sum(1 for finding in findings if finding["finding_type"] == "stale_access"),
        "privileged_account_count": sum(1 for finding in findings if finding["finding_type"] == "privileged_account"),
        "unresolved_exception_count": sum(1 for finding in findings if finding["finding_type"] == "unresolved_exception"),
    }


_TYPE_ORDER = {"excessive_privileges": 0, "stale_access": 1, "privileged_account": 2, "unresolved_exception": 3, "other": 4}
_STATUS_ORDER = {"open": 0, "exception": 1, "remediated": 2}
_RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def _finding_sort_key(finding: dict[str, Any]) -> tuple[int, int, int, str, str, str]:
    return (
        _STATUS_ORDER[finding["status"]],
        _TYPE_ORDER[finding["finding_type"]],
        _RISK_ORDER[finding["risk_level"]],
        finding["system"].lower(),
        finding["dataset"].lower(),
        finding["principal"].lower(),
    )


def _group_worst_key(findings: list[dict[str, Any]]) -> tuple[int, int, int]:
    first = min(findings, key=_finding_sort_key)
    return (_STATUS_ORDER[first["status"]], _TYPE_ORDER[first["finding_type"]], _RISK_ORDER[first["risk_level"]])


def _finding_type(value: Any) -> FindingType:
    text = _text(value).lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "excessive": "excessive_privileges",
        "excessive_privilege": "excessive_privileges",
        "overprivileged": "excessive_privileges",
        "stale": "stale_access",
        "privileged": "privileged_account",
        "privileged_accounts": "privileged_account",
        "exception": "unresolved_exception",
    }
    text = aliases.get(text, text)
    if text in _TYPE_ORDER:
        return text  # type: ignore[return-value]
    return "other"


def _status(value: Any, *, finding_type: FindingType) -> FindingStatus:
    text = _text(value).lower()
    if text in {"remediated", "resolved", "closed"}:
        return "remediated"
    if text in {"exception", "accepted", "risk accepted"}:
        return "exception"
    if finding_type == "unresolved_exception":
        return "exception"
    return "open"


def _risk(value: Any, *, finding_type: FindingType) -> RiskLevel:
    text = _text(value).lower()
    if text in _RISK_ORDER:
        return text  # type: ignore[return-value]
    defaults: dict[FindingType, RiskLevel] = {
        "excessive_privileges": "high",
        "stale_access": "medium",
        "privileged_account": "high",
        "unresolved_exception": "medium",
        "other": "unknown",
    }
    return defaults[finding_type]


def _recommended_remediation(finding_type: FindingType) -> str:
    if finding_type == "excessive_privileges":
        return "Reduce access to least privilege and record approver sign-off."
    if finding_type == "stale_access":
        return "Remove inactive access or revalidate business need with the owner."
    if finding_type == "privileged_account":
        return "Confirm privileged account ownership, MFA, and break-glass justification."
    if finding_type == "unresolved_exception":
        return "Resolve or formally re-approve the exception with expiry and compensating controls."
    return "Assign an owner, document access rationale, and track remediation to closure."


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return sorted({_text(item) for item in values if _text(item)}, key=str.lower)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
