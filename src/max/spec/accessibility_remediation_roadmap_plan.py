"""Generate deterministic accessibility remediation roadmap plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact, string_list
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.accessibility_remediation_roadmap_plan.v1"
KIND = "max.spec.accessibility_remediation_roadmap_plan"
SEVERITY_ORDER = {"blocker": 0, "critical": 1, "high": 2, "medium": 3, "low": 4}


def generate_accessibility_remediation_roadmap_plan(inputs: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(inputs, "accessibility_remediation_roadmap")
    findings = unique_records(named(hints.get("findings") or hints.get("issues"), ("issue", "name", "wcag")), [{"issue": "accessibility review item", "severity": "medium"}])
    issue_inventory = sorted((_issue_row(record, index, evidence_ids) for index, record in enumerate(findings, start=1)), key=lambda item: (SEVERITY_ORDER.get(item["severity"], 5), item["name"].casefold()))
    gaps = [item for item in issue_inventory if item["evidence_gap"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, issue_count=len(issue_inventory), blocker_count=sum(1 for item in issue_inventory if item["severity"] == "blocker"), evidence_gap_count=len(gaps)),
        "issue_inventory": issue_inventory,
        "severity_buckets": _buckets(issue_inventory),
        "owners": section(hints, ("owners", "owner_assignments"), "ARO", "accessibility_owner", "Assign remediation owner", evidence_ids, ["design, frontend, QA, product, and support owners"]),
        "acceptance_checks": section(hints, ("acceptance_checks", "checks"), "ARA", "qa_owner", "Run accessibility acceptance check", evidence_ids, ["keyboard, screen reader, contrast, focus, and regression checks"]),
        "release_sequencing": section(hints, ("release_sequencing", "sequencing"), "ARR", "release_owner", "Sequence accessibility remediation release", evidence_ids, ["blockers before launch, critical next patch, remaining issues in planned releases"]),
        "verification_evidence": section(hints, ("verification_evidence", "evidence"), "ARV", "qa_owner", "Collect accessibility verification evidence", evidence_ids, ["axe results, manual assistive tech notes, screenshots, and acceptance sign-off"]),
        "evidence_gaps": gaps,
        "evidence_references": ctx["evidence_references"],
    }


def _issue_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    severity = compact(record.get("severity")).lower() or "medium"
    if severity not in SEVERITY_ORDER:
        severity = "medium"
    wcag = compact(record.get("wcag") or record.get("wcag_reference"))
    flows = _unique_casefold(string_list(record.get("affected_flows") or record.get("flows"))) or ["primary user flow"]
    return row("ARI", index, compact(record.get("issue") or record.get("name")) or "accessibility review item", compact(record.get("owner")) or "accessibility_owner", "Remediate accessibility finding and verify user impact.", evidence_ids, severity=severity, wcag_impact=wcag or "missing WCAG reference", affected_flows=flows, evidence_gap=not bool(wcag))


def _buckets(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {severity: [item["name"] for item in items if item["severity"] == severity] for severity in SEVERITY_ORDER if any(item["severity"] == severity for item in items)}


def _unique_casefold(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in sorted(values, key=str.casefold):
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
