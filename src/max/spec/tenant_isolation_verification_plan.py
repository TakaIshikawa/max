"""Generate deterministic tenant isolation verification plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-tenant-isolation-verification-plan/v1"
KIND = "max.spec.tenant_isolation_verification_plan"


def generate_tenant_isolation_verification_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "tenant_isolation_verification")
    boundaries = _rows(plan.get("isolation_boundaries") or plan.get("boundaries") or spec.get("isolation_boundaries"), "boundary", "TIV-B")
    if not boundaries:
        boundaries = [{"id": "TIV-B001", "boundary": "tenant-boundary-required", "status": "blocked", "owner": "owner-required"}]
    checks = _rows(plan.get("verification_checks") or spec.get("verification_checks"), "check", "TIV-C")
    negatives = _rows(plan.get("negative_tests") or spec.get("negative_tests"), "test", "TIV-N")
    risks = _rows(plan.get("shared_resource_risks") or plan.get("shared_infrastructure") or spec.get("shared_resource_risks"), "resource", "TIV-R")
    owners = _rows(plan.get("owners") or spec.get("owners"), "owner", "TIV-O")
    evidence = _evidence(plan, spec)
    gaps = _gaps(boundaries, negatives, owners, evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "verified_count": sum(1 for row in boundaries if _status(row) == "verified"),
            "partial_count": sum(1 for row in boundaries if _status(row) == "partial"),
            "blocked_count": sum(1 for row in boundaries if _status(row) == "blocked") + len(gaps),
        },
        "isolation_boundaries": boundaries,
        "verification_checks": checks,
        "negative_tests": negatives,
        "shared_resource_risks": risks,
        "owner_assignments": owners,
        "evidence_references": evidence,
        "release_blocking_gaps": gaps,
    }


def render_tenant_isolation_verification_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if isinstance(plan_or_spec, dict) and plan_or_spec.get("kind") == KIND else generate_tenant_isolation_verification_plan(plan_or_spec)
    lines = ["# Tenant Isolation Verification Plan", ""]
    for title, key, label in (
        ("Isolation Boundaries", "isolation_boundaries", "boundary"),
        ("Verification Checks", "verification_checks", "check"),
        ("Negative Tests", "negative_tests", "test"),
        ("Shared Resource Risks", "shared_resource_risks", "resource"),
        ("Release Blocking Gaps", "release_blocking_gaps", "gap"),
    ):
        _section(lines, title, plan[key], label)
    return "\n".join(lines).rstrip() + "\n"


def _gaps(boundaries: list[dict[str, str]], negatives: list[dict[str, str]], owners: list[dict[str, str]], evidence: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if not negatives:
        gaps.append({"gap": "missing negative tests", "severity": "release-blocking", "owner": "security_owner"})
    if not owners or any(row.get("owner") == "owner-required" for row in boundaries):
        gaps.append({"gap": "missing owner evidence", "severity": "release-blocking", "owner": "engineering_owner"})
    if not evidence:
        gaps.append({"gap": "missing observability evidence", "severity": "release-blocking", "owner": "observability_owner"})
    return _numbered(gaps, "TIV-G")


def _status(row: dict[str, str]) -> str:
    status = _text(row.get("status")).casefold()
    if status in {"verified", "pass", "passed"}:
        return "verified"
    if status in {"partial", "in-progress", "at-risk"}:
        return "partial"
    return "blocked"


def _rows(value: Any, key: str, prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = {str(k): _text(v) for k, v in (item.items() if isinstance(item, dict) else [(key, item)]) if _text(v)}
        label = row.get(key) or row.get("name")
        if label:
            row[key] = label
            rows.append(row)
    return _numbered(sorted(rows, key=lambda row: row[key].casefold()), prefix)


def _evidence(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    refs = _values(plan.get("evidence_references") or plan.get("observability_evidence") or spec.get("evidence_references"))
    return [{"id": f"TIV-E{index:03d}", "reference": ref} for index, ref in enumerate(sorted(dict.fromkeys(refs), key=str.casefold), start=1)]


def _section(lines: list[str], title: str, rows: list[dict[str, str]], label: str) -> None:
    lines.extend([f"## {title}", ""])
    lines.extend(f"- {row['id']}: {row.get(label)}" for row in rows)
    if not rows:
        lines.append("- None.")
    lines.append("")


def _nested(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    return _dict(spec.get(key) or metadata.get(key))


def _numbered(rows: list[dict[str, str]], prefix: str) -> list[dict[str, str]]:
    for index, row in enumerate(rows, start=1):
        row["id"] = f"{prefix}{index:03d}"
    return rows


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _values(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [_text(item) for item in values if _text(item)]


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
