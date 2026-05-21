"""Deterministic security review remediation plans for design brief mappings."""

from __future__ import annotations

import json
from typing import Any

from max.analysis._design_brief_plan_common import dedupe, join_text, list_values, text

KIND = "max.design_brief.security_review_remediation_plan"
SCHEMA_VERSION = "max.design_brief.security_review_remediation_plan.v1"

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
_BLOCKING_SEVERITIES = {"critical", "high"}
_RESOLVED_STATUSES = {"accepted", "closed", "complete", "completed", "done", "fixed", "mitigated", "resolved"}


def build_design_brief_security_review_remediation_plan(brief: dict[str, Any]) -> dict[str, Any]:
    actions = _remediation_actions(brief)
    evidence_gaps = _evidence_gaps(actions)
    approval_owners = _approval_owners(brief, actions)
    unresolved_actions = [row for row in actions if not row["resolved"]]
    blocking_actions = [
        row for row in unresolved_actions if row["severity"] in _BLOCKING_SEVERITIES
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(brief),
        "design_brief": _brief_block(brief),
        "summary": {
            "readiness_status": "ready_for_security_approval"
            if not blocking_actions and not evidence_gaps and approval_owners
            else "blocked_pending_security_remediation",
            "finding_count": len(actions),
            "open_finding_count": len(unresolved_actions),
            "blocking_finding_count": len(blocking_actions),
            "evidence_gap_count": len(evidence_gaps),
            "approval_owner_count": len(approval_owners),
            "severity_counts": _severity_counts(actions),
        },
        "remediation_actions": actions,
        "actions_by_severity": _group_actions(actions, "severity"),
        "actions_by_owner": _group_actions(actions, "owner"),
        "unresolved_evidence_gaps": evidence_gaps,
        "approval_owners": approval_owners,
        "recommendation": _recommendation(blocking_actions, evidence_gaps, approval_owners),
    }


def render_design_brief_security_review_remediation_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported security review remediation plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Security Review Remediation Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Recommendation: `{report['recommendation']['status']}`",
        "",
        "## Readiness Summary",
        "",
        f"- Readiness status: {summary['readiness_status']}",
        f"- Findings: {summary['finding_count']}",
        f"- Open findings: {summary['open_finding_count']}",
        f"- Blocking findings: {summary['blocking_finding_count']}",
        f"- Evidence gaps: {summary['evidence_gap_count']}",
        f"- Approval owners: {summary['approval_owner_count']}",
        "",
        "## Prioritized Remediation Actions",
        "",
    ]
    if not report["remediation_actions"]:
        lines.append("- None")
    for row in report["remediation_actions"]:
        lines.append(
            f"- **{row['id']} {row['finding']}**: severity: {row['severity']}; "
            f"owner: {row['owner']}; due: {row['due_window']}; "
            f"status: {row['status']}; evidence: {join_text(row['evidence_refs'], 'missing')}; "
            f"action: {row['action']}"
        )

    lines.extend(["", "## Unresolved Evidence Gaps", ""])
    if not report["unresolved_evidence_gaps"]:
        lines.append("- None")
    for gap in report["unresolved_evidence_gaps"]:
        lines.append(f"- **{gap['id']} {gap['finding']}**: {gap['description']}")

    lines.extend(["", "## Approval Owners", ""])
    if not report["approval_owners"]:
        lines.append("- None")
    for owner in report["approval_owners"]:
        lines.append(f"- **{owner['id']} {owner['owner']}**: {owner['action']}")
    return "\n".join(lines).rstrip() + "\n"


def security_review_remediation_plan_filename(
    brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(text(brief.get('id'), 'design-brief'))}-"
        f"{_filename_part(text(brief.get('title'), 'Security Review Remediation Plan'))}-"
        f"security-review-remediation-plan.{extension}"
    )


def _remediation_actions(brief: dict[str, Any]) -> list[dict[str, Any]]:
    findings = _finding_rows(brief)
    actions = [_normalize_finding(row, idx) for idx, row in enumerate(findings, 1)]
    return sorted(
        actions,
        key=lambda row: (
            _SEVERITY_ORDER[row["severity"]],
            row["resolved"],
            row["owner"].lower(),
            row["finding"].lower(),
            row["id"],
        ),
    )


def _finding_rows(brief: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "security_findings",
        "security_review_findings",
        "findings",
        "remediation_findings",
    ):
        value = brief.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"finding": item} for item in value]
        if isinstance(value, dict):
            return [value]
    return []


def _normalize_finding(row: dict[str, Any], idx: int) -> dict[str, Any]:
    severity = _severity(row.get("severity") or row.get("risk") or row.get("priority"))
    status = _status(row.get("status") or row.get("resolution"))
    evidence_refs = dedupe(
        [
            *list_values(row.get("evidence_refs")),
            *list_values(row.get("evidence")),
            *list_values(row.get("source_ids")),
            *list_values(row.get("source_id")),
        ]
    )
    finding = text(
        row.get("finding") or row.get("title") or row.get("name") or row.get("risk"),
        f"Security finding {idx}",
    )
    return {
        "id": text(row.get("id") or row.get("finding_id"), f"SRR{idx}"),
        "finding": finding,
        "severity": severity,
        "owner": text(row.get("owner") or row.get("assignee"), "Security owner"),
        "due_window": text(row.get("due_window") or row.get("due") or row.get("target"), _due_window(severity)),
        "evidence_refs": evidence_refs,
        "status": status,
        "resolved": status in _RESOLVED_STATUSES,
        "action": text(row.get("action") or row.get("remediation"), f"Remediate and verify: {finding}"),
        "approval_owner": text(row.get("approval_owner") or row.get("approver"), ""),
    }


def _severity(value: Any) -> str:
    lowered = text(value, "unknown").lower()
    for severity in ("critical", "high", "medium", "low"):
        if severity in lowered:
            return severity
    return "unknown"


def _status(value: Any) -> str:
    lowered = text(value, "open").lower().replace(" ", "_")
    if lowered in {"in_progress", "needs_review", "open", "blocked", "accepted"}:
        return lowered
    return lowered or "open"


def _due_window(severity: str) -> str:
    return {
        "critical": "0-3 days",
        "high": "1 week",
        "medium": "2 weeks",
        "low": "next release",
    }.get(severity, "triage required")


def _evidence_gaps(actions: list[dict[str, Any]]) -> list[dict[str, str]]:
    gaps = []
    if not actions:
        gaps.append(
            {
                "id": "missing_security_findings",
                "finding": "Security review findings",
                "description": "Security finding evidence is missing.",
            }
        )
    for row in actions:
        if row["resolved"] or row["evidence_refs"]:
            continue
        gaps.append(
            {
                "id": f"{row['id']}_missing_evidence",
                "finding": row["finding"],
                "description": "Attach evidence refs before approval.",
            }
        )
    return gaps


def _approval_owners(brief: dict[str, Any], actions: list[dict[str, Any]]) -> list[dict[str, str]]:
    owners = dedupe(
        [
            *list_values(brief.get("approval_owners")),
            *list_values(brief.get("security_approval_owners")),
            *list_values(brief.get("security_approvers")),
            *[row["approval_owner"] for row in actions if row.get("approval_owner")],
        ]
    )
    return [
        {
            "id": f"A{idx}",
            "owner": owner,
            "action": f"{owner} approves remediation closure and residual risk.",
        }
        for idx, owner in enumerate(owners, 1)
    ]


def _severity_counts(actions: list[dict[str, Any]]) -> dict[str, int]:
    return {severity: sum(1 for row in actions if row["severity"] == severity) for severity in _SEVERITY_ORDER}


def _group_actions(actions: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = {}
    for row in actions:
        groups.setdefault(text(row.get(field), "unknown"), []).append(row["id"])
    return [
        {"id": f"{field}_{_filename_part(name)}", field: name, "action_ids": groups[name]}
        for name in sorted(groups)
    ]


def _recommendation(
    blocking_actions: list[dict[str, Any]],
    evidence_gaps: list[dict[str, str]],
    approval_owners: list[dict[str, str]],
) -> dict[str, str]:
    status = (
        "ready_for_security_approval"
        if not blocking_actions and not evidence_gaps and approval_owners
        else "blocked_pending_security_remediation"
    )
    return {
        "status": status,
        "rationale": (
            f"{len(blocking_actions)} blocking remediation action(s), "
            f"{len(evidence_gaps)} evidence gap(s), and "
            f"{len(approval_owners)} approval owner(s) recorded."
        ),
        "next_action": "Run security approval review." if status == "ready_for_security_approval" else "Close blocking actions and evidence gaps.",
    }


def _source(brief: dict[str, Any]) -> dict[str, str]:
    return {
        "project": "max",
        "entity_type": "design_brief",
        "id": text(brief.get("id"), "design-brief"),
        "generated_at": text(brief.get("updated_at") or brief.get("created_at")),
    }


def _brief_block(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": text(brief.get("id"), "design-brief"),
        "title": text(brief.get("title"), "Design brief"),
        "domain": text(brief.get("domain")),
        "theme": text(brief.get("theme")),
        "source_idea_ids": list_values(brief.get("source_idea_ids")),
    }


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
