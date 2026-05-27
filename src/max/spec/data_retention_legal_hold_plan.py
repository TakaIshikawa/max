"""Generate deterministic data retention legal hold plans."""

from __future__ import annotations

from datetime import date
from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact, markdown_header, render_evidence, render_item
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.data_retention_legal_hold_plan.v1"
KIND = "max.spec.data_retention_legal_hold_plan"
SECTIONS = (
    "data_domains",
    "hold_scope",
    "custodians",
    "retention_conflicts",
    "approval_workflow",
    "release_criteria",
    "audit_evidence",
    "monitoring_cadence",
    "findings",
)


def generate_data_retention_legal_hold_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_retention_legal_hold")
    domains = unique_records(named(hints.get("data_domains") or hints.get("domains") or hints.get("datasets"), ("domain", "dataset", "system")), [{"name": "records subject to legal hold", "owner": "legal_owner", "status": "active"}])
    custodians = unique_records(named(hints.get("custodians") or hints.get("owners"), ("custodian", "owner", "team")), [{"name": "legal hold owner", "status": "assigned"}])
    conflicts = unique_records(named(hints.get("retention_conflicts") or hints.get("conflicts") or hints.get("deletion_policies"), ("conflict", "policy", "dataset")), [])
    domain_rows = [_domain_row(record, index, evidence_ids) for index, record in enumerate(domains, start=1)]
    custodian_rows = [_custodian_row(record, index, evidence_ids) for index, record in enumerate(custodians, start=1)]
    conflict_rows = [_conflict_row(record, index, evidence_ids) for index, record in enumerate(conflicts, start=1)]
    findings = [*[_finding(item, len([]) + index, evidence_ids) for index, item in enumerate(domain_rows + custodian_rows, start=1) if item.get("review_status") in {"expired", "unknown"}], *conflict_rows]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, data_domain_count=len(domain_rows), custodian_count=len(custodian_rows), retention_conflict_count=len(conflict_rows), finding_count=len(findings)),
        "data_domains": domain_rows,
        "hold_scope": section(hints, ("hold_scope", "scope"), "LHS", "legal_owner", "Define legal hold scope", evidence_ids, ["matters, accounts, data domains, date range, and preservation obligations"], extra_keys=("matter", "account", "date_range")),
        "custodians": custodian_rows,
        "retention_conflicts": conflict_rows,
        "approval_workflow": section(hints, ("approval_workflow", "approvals"), "LHA", "legal_owner", "Approve legal hold", evidence_ids, ["legal, privacy, security, records, and business owner approval"], extra_keys=("approver", "status")),
        "release_criteria": section(hints, ("release_criteria", "release"), "LHR", "legal_owner", "Define release criteria", evidence_ids, ["matter closure, legal approval, custodian notice, and deletion queue release"], extra_keys=("condition",)),
        "audit_evidence": section(hints, ("audit_evidence", "evidence"), "LHE", "compliance_owner", "Collect legal hold audit evidence", evidence_ids, ["hold notice, approval record, preservation control, custodian attestation, and release approval"]),
        "monitoring_cadence": section(hints, ("monitoring_cadence", "cadence", "monitoring"), "LHM", "records_owner", "Monitor legal hold", evidence_ids, ["monthly custodian, preservation, deletion queue, and expiry review"], extra_keys=("cadence", "next_review")),
        "findings": findings,
        "evidence_references": ctx["evidence_references"],
    }


def render_data_retention_legal_hold_plan_markdown(plan: dict[str, Any]) -> str:
    lines = markdown_header(plan, "Data Retention Legal Hold Plan")
    for section_name in SECTIONS:
        title = section_name.replace("_", " ").title()
        lines.extend([f"## {title}", ""])
        rows = plan.get(section_name) or []
        if not rows:
            lines.extend(["None.", ""])
            continue
        renderer = render_evidence if section_name == "evidence_references" else render_item
        for record in rows:
            lines.extend(renderer(record))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _domain_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    expiry = compact(record.get("expiry") or record.get("expires_at") or record.get("hold_until"))
    status = _status(record.get("status"), expiry)
    return item("LHD", index, record, "records_owner", evidence_ids, "Preserve data domain under legal hold", name_keys=("name", "domain", "dataset", "system"), extra_keys=("domain", "dataset", "system", "hold_until", "legal_matter")) | {"review_status": status}


def _custodian_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    name = compact(record.get("name") or record.get("custodian") or record.get("owner") or record.get("team"))
    status = "unknown" if not name or name.lower() in {"unknown", "tbd"} else compact(record.get("status")).lower() or "assigned"
    return item("LHC", index, record | {"name": name or "unknown custodian"}, "legal_owner", evidence_ids, "Assign legal hold custodian", name_keys=("name", "custodian", "owner", "team"), extra_keys=("team", "role", "attestation")) | {"review_status": status}


def _conflict_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    return item("LHF", index, record, "records_owner", evidence_ids, "Remediate retention deletion policy conflict", name_keys=("name", "conflict", "policy", "dataset"), extra_keys=("policy", "dataset", "remediation")) | {"review_status": "conflict", "remediation": compact(record.get("remediation")) or "pause deletion policy until legal hold release is approved"}


def _finding(source: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    return row("LHG", index, source["name"], source.get("owner") or "legal_owner", f"Resolve legal hold finding for {source['name']}.", evidence_ids, severity="high", status=source.get("review_status") or "unknown")


def _status(raw_status: Any, expiry: str) -> str:
    status = compact(raw_status).lower()
    if status:
        return status
    if expiry:
        try:
            return "expired" if date.fromisoformat(expiry) < date.today() else "active"
        except ValueError:
            return "active"
    return "unknown"
