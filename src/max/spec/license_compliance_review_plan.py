"""Generate deterministic license compliance review plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-license-compliance-review-plan/v1"
KIND = "max.spec.license_compliance_review_plan"
STATUS_ORDER = {"denied": 0, "unknown": 1, "review-required": 2, "allowed": 3}


def generate_license_compliance_review_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    policy = _policy(spec)
    rows = _component_rows(spec, policy)
    violations = [row for row in rows if row["license_status"] == "denied"]
    approval_queue = [row for row in rows if row["license_status"] in {"unknown", "review-required"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "component_count": len(rows),
            "denied_count": len(violations),
            "review_required_count": len(approval_queue),
            "allowed_count": sum(1 for row in rows if row["license_status"] == "allowed"),
        },
        "component_rows": rows,
        "policy_violations": violations,
        "approval_queue": approval_queue,
        "remediation_actions": _remediation_actions(rows),
    }


def render_license_compliance_review_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_license_compliance_review_plan(plan_or_spec)
    lines = ["# License Compliance Review Plan", "", f"Schema version: {plan['schema_version']}", "", "## Component Review", ""]
    for row in plan["component_rows"]:
        lines.append(f"- {row['id']}: {row['component']} license={row['license']} status={row['license_status']} owner={row['owner']}")
    lines.extend(["", "## Policy Violations", ""])
    if plan["policy_violations"]:
        for row in plan["policy_violations"]:
            lines.append(f"- {row['id']}: {row['component']} uses denied license {row['license']}")
    else:
        lines.append("- No denied licenses identified.")
    lines.extend(["", "## Approval Queue", ""])
    if plan["approval_queue"]:
        for row in plan["approval_queue"]:
            lines.append(f"- {row['id']}: {row['component']} requires {row['license_status']} approval")
    else:
        lines.append("- No approvals required.")
    lines.extend(["", "## Remediation Actions", ""])
    for action in plan["remediation_actions"]:
        lines.append(f"- {action['component_id']}: {action['action']} owner={action['owner']}")
    return "\n".join(lines).rstrip() + "\n"


def _component_rows(spec: dict[str, Any], policy: dict[str, set[str]]) -> list[dict[str, str]]:
    rows = []
    for index, raw in enumerate(_raw_components(spec), start=1):
        license_name = _text(raw.get("license") or raw.get("license_name"))
        status = _status(license_name, policy)
        rows.append({"id": "", "component": _text(raw.get("component") or raw.get("dependency") or raw.get("name")) or f"component-{index}", "license": license_name or "unknown", "usage_type": _text(raw.get("usage_type") or raw.get("usage")) or "runtime", "owner": _text(raw.get("owner")) or "license_compliance_owner", "license_status": status, "remediation_action": _text(raw.get("remediation_action") or raw.get("remediation")) or _default_action(status)})
    if not rows:
        rows.append({"id": "", "component": "component-intake", "license": "unknown", "usage_type": "runtime", "owner": "license_compliance_owner", "license_status": "unknown", "remediation_action": _default_action("unknown")})
    rows = sorted(rows, key=lambda row: (STATUS_ORDER[row["license_status"]], row["component"].casefold(), row["license"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"LCR-{index:03d}"
    return rows


def _raw_components(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get("license_compliance_review") or spec.get("license_compliance_review"))
    candidates = plan.get("components") or plan.get("dependencies") or metadata.get("components") or spec.get("components") or spec.get("dependencies")
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _policy(spec: dict[str, Any]) -> dict[str, set[str]]:
    metadata = _dict(spec.get("metadata"))
    policy = _dict(metadata.get("policy") or spec.get("policy"))
    return {
        "allowed": {_text(item).casefold() for item in _values(policy.get("allow") or policy.get("allowed") or spec.get("allowed_licenses"), ["mit", "apache-2.0", "bsd-3-clause"])},
        "denied": {_text(item).casefold() for item in _values(policy.get("deny") or policy.get("denied") or spec.get("denied_licenses"), ["gpl-3.0", "agpl-3.0"])},
        "review": {_text(item).casefold() for item in _values(policy.get("review") or policy.get("review_required"), [])},
    }


def _status(license_name: str, policy: dict[str, set[str]]) -> str:
    normalized = license_name.casefold()
    if not normalized:
        return "unknown"
    if normalized in policy["denied"]:
        return "denied"
    if normalized in policy["allowed"]:
        return "allowed"
    if normalized in policy["review"]:
        return "review-required"
    return "unknown"


def _remediation_actions(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"component_id": row["id"], "component": row["component"], "owner": row["owner"], "action": row["remediation_action"]} for row in rows if row["license_status"] != "allowed"]


def _default_action(status: str) -> str:
    if status == "denied":
        return "replace component or obtain legal exception"
    if status == "review-required":
        return "submit license approval request"
    return "identify license and submit compliance review"


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "component_rows" in value


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
