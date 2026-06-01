"""Generate deterministic customer environment isolation review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.customer_environment_isolation_review_plan.v1"
KIND = "max.spec.customer_environment_isolation_review_plan"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_customer_environment_isolation_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    environments = _required_list(hints.get("environments"), "environments")
    controls = _required_list(hints.get("isolation_controls"), "isolation controls")
    dependencies = _required_list(hints.get("shared_dependencies"), "shared dependencies")
    boundaries = _required_list(hints.get("data_boundaries"), "data boundaries")
    evidence = _evidence(hints.get("test_evidence"))
    findings = _findings(hints.get("findings"), environments, dependencies, evidence)
    refs = [item["id"] for item in ctx["evidence_references"]]
    remediation = [finding for finding in findings if finding["severity"] in {"critical", "high"} or finding["status"] in {"failed", "missing"}]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, environment_count=len(environments), shared_dependency_count=len(dependencies), finding_count=len(findings), remediation_count=len(remediation)),
        "environment_reviews": [_row("CER", i, environment, "isolation_owner", f"Review isolation controls for {environment}.", refs, isolation_controls=controls, data_boundaries=boundaries) for i, environment in enumerate(environments, 1)],
        "shared_dependency_findings": [_row("CED", i, dependency, "platform_owner", f"Assess shared dependency isolation risk for {dependency}.", refs, environments=environments) for i, dependency in enumerate(dependencies, 1)],
        "test_evidence": [_row("CET", i, item["name"], item["owner"], f"Validate isolation evidence status: {item['status']}.", refs, status=item["status"], environment=item["environment"]) for i, item in enumerate(evidence, 1)],
        "findings": [_finding_row(i, finding, refs) for i, finding in enumerate(findings, 1)],
        "remediation_actions": [_row("CEA", i, finding["name"], finding["owner"], f"Remediate {finding['severity']} isolation finding for {finding['environment']} and {finding['shared_dependency']}.", refs, severity=finding["severity"], gate_required=True) for i, finding in enumerate(remediation, 1)],
        "remediation_gates": [_row("CEG", i, finding["name"], finding["owner"], "Gate approval until isolation evidence passes and shared dependency risk is accepted or removed.", refs, status="blocked", severity=finding["severity"]) for i, finding in enumerate(remediation, 1)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("customer_environment_isolation_review")
    return value if isinstance(value, dict) else {}


def _required_list(value: Any, label: str) -> list[str]:
    values = sorted(dict.fromkeys(item for item in string_list(value) if item), key=str.casefold)
    if not values:
        raise ValueError(f"customer_environment_isolation_review requires {label}")
    return values


def _evidence(value: Any) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    result = []
    for index, item in enumerate(raw, 1):
        record = item if isinstance(item, dict) else {"name": item}
        result.append({"name": compact(record.get("name")) or f"test evidence {index}", "environment": compact(record.get("environment")) or "all environments", "status": compact(record.get("status")).lower() or "missing", "owner": compact(record.get("owner")) or "qa_owner"})
    return sorted(result, key=lambda item: (item["environment"].casefold(), item["name"].casefold()))


def _findings(value: Any, environments: list[str], dependencies: list[str], evidence: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = value if isinstance(value, list) else []
    result = []
    for index, item in enumerate(raw, 1):
        record = item if isinstance(item, dict) else {"name": item}
        result.append(_finding(record, index))
    for item in evidence:
        if item["status"] in {"failed", "missing"}:
            result.append(_finding({"name": f"{item['environment']} {item['status']} isolation evidence", "environment": item["environment"], "shared_dependency": dependencies[0], "severity": "high" if item["status"] == "failed" else "medium", "status": item["status"], "owner": item["owner"]}, len(result) + 1))
    if not result:
        for environment in environments:
            result.append(_finding({"name": f"{environment} isolation review", "environment": environment, "shared_dependency": dependencies[0], "severity": "low", "status": "pending"}, len(result) + 1))
    return sorted(result, key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), item["environment"].casefold(), item["shared_dependency"].casefold(), item["name"].casefold()))


def _finding(record: dict[str, Any], index: int) -> dict[str, str]:
    severity = compact(record.get("severity")).lower() or "medium"
    status = compact(record.get("status")).lower() or "open"
    return {"name": compact(record.get("name")) or f"isolation finding {index}", "environment": compact(record.get("environment")) or "environment", "shared_dependency": compact(record.get("shared_dependency") or record.get("dependency")) or "shared dependency", "severity": severity, "status": status, "owner": compact(record.get("owner")) or "isolation_owner"}


def _finding_row(index: int, finding: dict[str, str], refs: list[str]) -> dict[str, Any]:
    return _row("CEF", index, finding["name"], finding["owner"], f"{finding['status']} finding in {finding['environment']} for {finding['shared_dependency']}.", refs, environment=finding["environment"], shared_dependency=finding["shared_dependency"], severity=finding["severity"], status=finding["status"])


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None, [])})
    return data
