"""Generate deterministic audit finding remediation plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-audit-finding-remediation-plan/v1"
KIND = "max.spec.audit_finding_remediation_plan"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
STATUS_VALUES = {"open", "in-progress", "blocked", "mitigated", "closed"}


def generate_audit_finding_remediation_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a stable audit finding remediation plan."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    rows = _finding_rows(spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "finding_count": len(rows),
            "severity_counts": _counts(rows, "severity"),
            "status_counts": _counts(rows, "status"),
            "blocked_count": sum(1 for row in rows if row["status"] == "blocked"),
        },
        "remediation_rows": rows,
        "escalation_items": _escalations(rows),
        "review_cadence": _review_cadence(spec, rows),
    }


def render_audit_finding_remediation_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    """Render an audit finding remediation plan as deterministic Markdown."""
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_audit_finding_remediation_plan(plan_or_spec)
    lines = [
        "# Audit Finding Remediation Plan",
        "",
        f"Schema version: {plan['schema_version']}",
        "",
        "## Findings",
        "",
    ]
    for row in plan["remediation_rows"]:
        lines.extend(
            [
                f"### {row['id']}: {row['finding']}",
                "",
                f"- Severity: {row['severity']}",
                f"- Status: {row['status']}",
                f"- Owner: {row['owner']}",
                f"- Due date: {row['due_date']}",
                f"- Control: {row['control']}",
                f"- Framework: {row['framework']}",
                "",
            ]
        )
    lines.extend(["## Remediation Actions", ""])
    for row in plan["remediation_rows"]:
        lines.append(f"- {row['id']}: {row['action']} ({row['owner']}, due {row['due_date']})")
    lines.extend(["", "## Escalations", ""])
    for item in plan["escalation_items"]:
        lines.append(f"- {item['finding_id']}: {item['reason']} -> {item['escalate_to']}")
    if not plan["escalation_items"]:
        lines.append("- No escalations required.")
    cadence = plan["review_cadence"]
    lines.extend(
        [
            "",
            "## Review Cadence",
            "",
            f"- Cadence: {cadence['cadence']}",
            f"- Next review: {cadence['next_review']}",
            f"- Reviewer: {cadence['reviewer']}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _finding_rows(spec: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, raw in enumerate(_raw_findings(spec), start=1):
        name = _text(raw.get("finding") or raw.get("name") or raw.get("title")) or f"finding-{index}"
        severity = _choice(raw.get("severity") or raw.get("risk"), set(SEVERITY_RANK), "medium")
        status = _choice(raw.get("status"), STATUS_VALUES, "open")
        owner = _text(raw.get("owner") or raw.get("assignee")) or "audit_remediation_owner"
        due_date = _text(raw.get("due_date") or raw.get("due") or raw.get("deadline")) or "next remediation review"
        control = _text(raw.get("control") or raw.get("control_ref") or raw.get("control_reference")) or "control-reference-required"
        framework = _text(raw.get("framework") or raw.get("standard")) or "framework-reference-required"
        action = _text(raw.get("action") or raw.get("remediation_action") or raw.get("remediation")) or "define corrective action and evidence owner"
        rows.append(
            {
                "id": "",
                "finding": name,
                "severity": severity,
                "status": status,
                "owner": owner,
                "due_date": due_date,
                "control": control,
                "framework": framework,
                "action": action,
            }
        )
    if not rows:
        rows.append(
            {
                "id": "",
                "finding": "audit finding intake",
                "severity": "medium",
                "status": "open",
                "owner": "audit_remediation_owner",
                "due_date": "next remediation review",
                "control": "control-reference-required",
                "framework": "framework-reference-required",
                "action": "define corrective action and evidence owner",
            }
        )
    rows = sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], _date_key(row["due_date"]), row["finding"].casefold(), row["control"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"AFR-{index:03d}"
    return rows


def _raw_findings(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    audit = _dict(metadata.get("audit_finding_remediation") or spec.get("audit_finding_remediation"))
    candidates = audit.get("findings") or metadata.get("audit_findings") or spec.get("findings")
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _escalations(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    items = []
    for row in rows:
        if row["severity"] in {"critical", "high"} or row["status"] == "blocked":
            reason = "blocked remediation" if row["status"] == "blocked" else f"{row['severity']} severity finding"
            items.append({"finding_id": row["id"], "reason": reason, "escalate_to": "security_governance_lead"})
    return items


def _review_cadence(spec: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, str]:
    cadence = _dict(_dict(spec.get("metadata")).get("review_cadence") or spec.get("review_cadence"))
    default_cadence = "weekly" if any(row["severity"] in {"critical", "high"} for row in rows) else "biweekly"
    return {
        "cadence": _text(cadence.get("cadence")) or default_cadence,
        "next_review": _text(cadence.get("next_review")) or "next remediation review",
        "reviewer": _text(cadence.get("reviewer")) or "audit_remediation_owner",
    }


def _counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[key]] = counts.get(row[key], 0) + 1
    return dict(sorted(counts.items()))


def _date_key(value: str) -> tuple[int, str]:
    return (1, value.casefold()) if value == "next remediation review" else (0, value.casefold())


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "remediation_rows" in value


def _choice(value: Any, allowed: set[str], fallback: str) -> str:
    text = _text(value).casefold()
    return text if text in allowed else fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
