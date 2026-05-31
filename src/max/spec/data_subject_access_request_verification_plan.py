"""Render deterministic DSAR verification plans as Markdown."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, unique_records

SCHEMA_VERSION = "max.spec.data_subject_access_request_verification_plan.v1"


def generate_data_subject_access_request_verification_plan(spec_like: Any) -> str:
    spec, _ctx, metadata_hints, _evidence_ids = base(spec_like, "data_subject_access_request_verification")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    requests = _records(hints.get("requests") or hints.get("dsars") or hints.get("subjects"), [{"name": "DSAR verification case", "owner": "privacy_owner", "severity": "medium"}])
    sections = [
        ("Identity Verification", "Confirm requester identity, authorization, jurisdiction, and fraud-review outcome before disclosure."),
        ("Data Inventory Lookup", "Search account, billing, support, telemetry, exports, and derived-profile stores for subject data coverage."),
        ("Response Packaging", "Package responsive data, redactions, exemptions, delivery channel, and requester-facing response evidence."),
        ("Exception Handling", "Escalate identity mismatch, legal hold, excessive request, missing inventory, or unsafe disclosure exceptions."),
        ("Audit Evidence", "Attach intake record, lookup manifest, reviewer notes, response artifact hash, and completion signoff."),
        ("Completion Signoff", "Record owner approval, response timestamp, unresolved exceptions, and retention location."),
    ]
    lines = [
        "# Data Subject Access Request Verification Plan",
        "",
        f"Schema: {SCHEMA_VERSION}",
        "",
        "| Request | Owner | Severity | Subject | Due |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in requests:
        lines.append(
            f"| {item['name']} | {item['owner']} | {item['severity']} | {item['subject']} | {item['due']} |"
        )
    for title, description in sections:
        lines.extend(["", f"## {title}", description])
    return "\n".join(lines)


def _records(value: Any, fallback: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in unique_records(named(value, ("request_id", "id", "subject", "requester")), fallback):
        rows.append(
            {
                "name": compact(item.get("name") or item.get("request_id") or item.get("id")) or "DSAR verification case",
                "owner": compact(item.get("owner")) or "privacy_owner",
                "severity": compact(item.get("severity")) or "medium",
                "subject": compact(item.get("subject") or item.get("data_subject") or item.get("requester")) or "unspecified subject",
                "due": compact(item.get("due") or item.get("deadline")) or "not scheduled",
            }
        )
    return sorted(rows, key=lambda item: (_severity_rank(item["severity"]), item["name"].casefold()))


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}.get(value.lower(), 4)
