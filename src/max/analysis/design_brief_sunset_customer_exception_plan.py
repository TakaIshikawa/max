"""Deterministic sunset customer exception plans for design brief mappings."""

from __future__ import annotations

import json
from typing import Any

from max.analysis._design_brief_plan_common import join_text, list_values, text

KIND = "max.design_brief.sunset_customer_exception_plan"
SCHEMA_VERSION = "max.design_brief.sunset_customer_exception_plan.v1"


def build_design_brief_sunset_customer_exception_plan(brief: dict[str, Any]) -> dict[str, Any]:
    exceptions = _exception_rows(brief)
    commitments = _support_commitments(brief)
    approvals = _approval_owners(brief)
    mitigations = _mitigation_steps(brief)
    warnings = _missing_evidence(exceptions, commitments, approvals, mitigations)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(brief),
        "design_brief": _brief_block(brief),
        "summary": {
            "recommendation_status": "ready_for_exception_review"
            if not warnings
            else "blocked_pending_exception_evidence",
            "exception_count": len(exceptions),
            "approval_owner_count": len(approvals),
            "missing_evidence_count": len(warnings),
        },
        "exception_summary": exceptions,
        "support_commitments": commitments,
        "approval_owners": approvals,
        "mitigation_steps": mitigations,
        "recommendation": _recommendation(warnings),
        "missing_evidence": warnings,
    }


def render_design_brief_sunset_customer_exception_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported sunset customer exception plan format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# Sunset Customer Exception Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Recommendation: `{report['recommendation']['status']}`",
    ]
    for key, title in (
        ("exception_summary", "Exception Summary"),
        ("support_commitments", "Support Commitments"),
        ("approval_owners", "Approval Owners"),
        ("mitigation_steps", "Mitigation Steps"),
        ("missing_evidence", "Missing Evidence"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
        for row in rows:
            label = row.get("customer") or row.get("name") or row.get("owner") or row.get("id")
            detail = (
                row.get("action")
                or row.get("description")
                or row.get("extension_window")
                or row.get("commitment")
            )
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def sunset_customer_exception_plan_filename(
    brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(text(brief.get('id'), 'design-brief'))}-"
        f"{_filename_part(text(brief.get('title'), 'Sunset Customer Exception Plan'))}-"
        f"sunset-customer-exception-plan.{extension}"
    )


def _exception_rows(brief: dict[str, Any]) -> list[dict[str, str]]:
    customers = _dedupe(
        [
            *_rows_as_text(brief.get("exception_customers")),
            *_rows_as_text(brief.get("customer_segments")),
            *_rows_as_text(brief.get("segments")),
        ]
    )
    windows = _dedupe(
        [
            *_rows_as_text(brief.get("extension_windows")),
            *_rows_as_text(brief.get("requested_extension_windows")),
            *_rows_as_text(brief.get("commitment_windows")),
        ]
    )
    impacts = _dedupe(
        [
            *_rows_as_text(brief.get("commercial_impact")),
            *_rows_as_text(brief.get("revenue_impact")),
            *_rows_as_text(brief.get("impact")),
        ]
    )
    owners = _dedupe([*_rows_as_text(brief.get("approval_owners")), *_rows_as_text(brief.get("owners"))])
    mitigations = _dedupe(
        [*_rows_as_text(brief.get("mitigation_steps")), *_rows_as_text(brief.get("mitigations"))]
    )
    rows = []
    for idx, customer in enumerate(customers, 1):
        rows.append(
            {
                "id": f"E{idx}",
                "customer": customer,
                "extension_window": _pick(windows, idx) or "extension window pending",
                "commercial_impact": _pick(impacts, idx) or "commercial impact pending",
                "approval_owner": _pick(owners, idx) or "approval owner pending",
                "mitigation": _pick(mitigations, idx) or "mitigation plan pending",
            }
        )
    return rows


def _support_commitments(brief: dict[str, Any]) -> list[dict[str, str]]:
    values = _dedupe(
        [
            *_rows_as_text(brief.get("support_commitments")),
            *_rows_as_text(brief.get("commitments")),
            *_rows_as_text(brief.get("support_plan")),
        ]
    )
    return [
        {
            "id": f"C{idx}",
            "name": "Support commitment",
            "commitment": value,
            "owner": _first_text(brief.get("support_owner"), brief.get("owner")) or "Support owner",
        }
        for idx, value in enumerate(values, 1)
    ]


def _approval_owners(brief: dict[str, Any]) -> list[dict[str, str]]:
    owners = _dedupe([*_rows_as_text(brief.get("approval_owners")), *_rows_as_text(brief.get("owners"))])
    return [
        {
            "id": f"A{idx}",
            "owner": owner,
            "name": "Exception approval",
            "action": f"{owner} approves extension scope, expiry, and customer commitment.",
        }
        for idx, owner in enumerate(owners, 1)
    ]


def _mitigation_steps(brief: dict[str, Any]) -> list[dict[str, str]]:
    values = _dedupe(
        [*_rows_as_text(brief.get("mitigation_steps")), *_rows_as_text(brief.get("mitigations"))]
    )
    return [
        {
            "id": f"M{idx}",
            "name": "Exception mitigation",
            "action": value,
            "owner": _first_text(brief.get("mitigation_owner"), brief.get("owner")) or "Mitigation owner",
        }
        for idx, value in enumerate(values, 1)
    ]


def _missing_evidence(
    exceptions: list[dict[str, str]],
    commitments: list[dict[str, str]],
    approvals: list[dict[str, str]],
    mitigations: list[dict[str, str]],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if not exceptions:
        warnings.append({"id": "missing_customer_evidence", "description": "Exception customer or segment evidence is missing."})
    if not exceptions or any(row["extension_window"] == "extension window pending" for row in exceptions):
        warnings.append({"id": "missing_commitment_window", "description": "Requested extension or commitment window is missing."})
    if not approvals:
        warnings.append({"id": "missing_approval_owner", "description": "Approval owner evidence is missing."})
    if not commitments:
        warnings.append({"id": "missing_support_commitment", "description": "Support commitment evidence is missing."})
    if not mitigations:
        warnings.append({"id": "missing_mitigation_plan", "description": "Mitigation plan evidence is missing."})
    return warnings


def _recommendation(warnings: list[dict[str, str]]) -> dict[str, str]:
    status = "ready_for_exception_review" if not warnings else "blocked_pending_exception_evidence"
    return {
        "status": status,
        "rationale": f"{len(warnings)} sunset exception evidence gap(s) remain.",
        "next_action": "Review and approve customer exceptions." if not warnings else "Collect missing exception evidence.",
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


def _rows_as_text(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [join_text([value.get("name"), value.get("window"), value.get("owner")], "")]
    return [cleaned for item in list_values(value) if (cleaned := text(item))]


def _pick(values: list[str], idx: int) -> str:
    if not values:
        return ""
    return values[min(idx - 1, len(values) - 1)]


def _first_text(*values: Any) -> str:
    return next((cleaned for value in values if (cleaned := text(value))), "")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = text(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
