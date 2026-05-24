"""Generate deterministic safety mitigation verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.safety_mitigation_verification_plan.v1"
KIND = "max.spec.safety_mitigation_verification_plan"


def generate_safety_mitigation_verification_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "safety_mitigation_verification")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    findings = unique_records(
        named(
            hints.get("findings") or hints.get("safety_findings") or hints.get("issues"),
            ("finding", "risk", "title"),
        ),
        [{"name": "safety finding", "finding": "safety finding", "severity": "high"}],
    )
    mapping = _mitigation_mapping(findings, hints, evidence_ids)
    blockers = _blockers(findings, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Safety Mitigation Verification Plan",
        "summary": source_summary(
            ctx,
            finding_count=len(findings),
            blocker_count=len(blockers),
        ),
        "finding_summary": [
            item(
                "SMF",
                index,
                record,
                "safety_owner",
                evidence_ids,
                "Summarize safety finding",
                name_keys=("name", "finding", "risk", "title"),
                extra_keys=("finding", "risk", "severity"),
            )
            for index, record in enumerate(findings, start=1)
        ],
        "mitigation_mapping": mapping,
        "verification_blockers": blockers,
        "test_evidence": section(
            hints,
            ("test_evidence", "evidence", "verification_evidence"),
            "SME",
            "quality_owner",
            "Review safety mitigation test evidence",
            evidence_ids,
            ["regression suite, adversarial replay, human review sample, and production telemetry evidence"],
        ),
        "residual_risk": section(
            hints,
            ("residual_risk", "residual_risks", "risk_acceptance"),
            "SMR",
            "safety_owner",
            "Assess residual safety risk",
            evidence_ids,
            ["document residual severity, affected cohorts, monitoring trigger, and accountable acceptor"],
        ),
        "rollback_criteria": section(
            hints,
            ("rollback_criteria", "rollback", "rollback_plan"),
            "SMB",
            "release_manager",
            "Define safety rollback criteria",
            evidence_ids,
            ["critical safety regression, mitigation bypass, monitor breach, or reviewer rejection"],
        ),
        "monitoring_follow_up": section(
            hints,
            ("monitoring_follow_up", "monitoring", "follow_up"),
            "SMM",
            "safety_owner",
            "Monitor verified safety mitigation",
            evidence_ids,
            ["post-release sampling, alert thresholds, reviewer queue audit, and weekly residual risk review"],
        ),
        "signoff": section(
            hints,
            ("signoff", "approvals", "approval_checklist"),
            "SMA",
            "program_owner",
            "Approve safety mitigation verification",
            evidence_ids,
            ["safety owner, model owner, quality owner, release manager, and risk acceptor signoff"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _mitigation_mapping(
    findings: list[dict[str, Any]], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    fallback_mitigations = _names(hints.get("mitigations") or hints.get("mitigation_actions"))
    fallback_steps = _names(hints.get("verification_steps") or hints.get("tests"))
    rows = []
    for index, record in enumerate(findings, start=1):
        finding = compact(record.get("name") or record.get("finding") or record.get("risk")) or "safety finding"
        mitigations = _names(record.get("mitigations") or record.get("mitigation") or record.get("actions")) or fallback_mitigations or ["mitigation owner confirms implemented control"]
        steps = _names(record.get("verification_steps") or record.get("tests") or record.get("test_evidence")) or fallback_steps or ["rerun safety regression and adversarial replay"]
        rows.append(
            row(
                "SMV",
                index,
                f"verify mitigations for {finding}",
                compact(record.get("owner")) or "safety_owner",
                f"Verify {len(mitigations)} mitigation(s) and {len(steps)} verification step(s) for {finding}.",
                evidence_ids,
                severity=compact(record.get("severity")) or "high",
                finding=finding,
                mitigations="; ".join(mitigations),
                verification_steps="; ".join(steps),
            )
        )
    return rows


def _blockers(findings: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for record in findings:
        finding = compact(record.get("name") or record.get("finding") or record.get("risk")) or "safety finding"
        if not compact(record.get("owner")):
            blockers.append(_blocker(len(blockers) + 1, finding, "missing owner", "Assign a safety mitigation owner before verification signoff.", evidence_ids))
        if not (
            compact(record.get("evidence"))
            or compact(record.get("test_evidence"))
            or compact(record.get("verification_evidence"))
        ):
            blockers.append(_blocker(len(blockers) + 1, finding, "missing evidence", "Attach mitigation test evidence before release approval.", evidence_ids))
    return blockers


def _blocker(
    index: int,
    finding: str,
    gap: str,
    description: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return row(
        "SMX",
        index,
        f"{gap}: {finding}",
        "safety_owner",
        description,
        evidence_ids,
        severity="critical",
        finding=finding,
        gap=gap,
    )


def _names(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif value:
        values = [value]
    else:
        values = []
    result = []
    for item_value in values:
        if isinstance(item_value, dict):
            text = compact(
                item_value.get("name")
                or item_value.get("mitigation")
                or item_value.get("step")
                or item_value.get("description")
            )
        else:
            text = compact(item_value)
        if text and text not in result:
            result.append(text)
    return result
