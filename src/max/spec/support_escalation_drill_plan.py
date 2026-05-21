"""Generate deterministic support escalation drill plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-support-escalation-drill-plan/v1"
KIND = "max.spec.support_escalation_drill_plan"


def generate_support_escalation_drill_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "support_escalation_drill")
    scenarios = _scenarios(plan, spec)
    tiers = _rows(plan.get("escalation_tiers") or spec.get("escalation_tiers"), "tier", "SED-T")
    paging = _rows(plan.get("paging_paths") or spec.get("paging_paths"), "path", "SED-P")
    comms = _rows(plan.get("customer_communication_checkpoints") or plan.get("communications") or spec.get("communications"), "checkpoint", "SED-C")
    criteria = _rows(plan.get("success_criteria") or spec.get("success_criteria"), "criterion", "SED-S")
    owners = _rows(plan.get("owners") or spec.get("owners"), "owner", "SED-O")
    evidence = _evidence(plan, spec)
    actions = _rows(plan.get("follow_up_actions") or spec.get("follow_up_actions"), "action", "SED-F")
    warnings = _warnings(scenarios, paging, comms, criteria)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "ready_count": sum(1 for row in scenarios if row["readiness"] == "ready"),
            "incomplete_count": sum(1 for row in scenarios if row["readiness"] == "incomplete"),
            "blocked_count": sum(1 for row in scenarios if row["readiness"] == "blocked") + len(warnings),
        },
        "scenarios": scenarios,
        "escalation_tiers": tiers,
        "paging_paths": paging,
        "customer_communication_checkpoints": comms,
        "success_criteria": criteria,
        "owners": owners,
        "evidence_links": evidence,
        "follow_up_actions": actions,
        "readiness_warnings": warnings,
    }


def render_support_escalation_drill_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if isinstance(plan_or_spec, dict) and plan_or_spec.get("kind") == KIND else generate_support_escalation_drill_plan(plan_or_spec)
    lines = ["# Support Escalation Drill Plan", ""]
    for title, key, label in (("Scenarios", "scenarios", "scenario"), ("Escalation Tiers", "escalation_tiers", "tier"), ("Paging Paths", "paging_paths", "path"), ("Customer Communication Checkpoints", "customer_communication_checkpoints", "checkpoint"), ("Success Criteria", "success_criteria", "criterion"), ("Follow-up Actions", "follow_up_actions", "action"), ("Warnings", "readiness_warnings", "warning")):
        _section(lines, title, plan[key], label)
    return "\n".join(lines).rstrip() + "\n"


def _scenarios(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = _rows(plan.get("scenarios") or spec.get("scenarios"), "scenario", "SED-D")
    if not rows:
        rows = [{"id": "SED-D001", "scenario": "support-scenario-required", "owner": "owner-required"}]
    for row in rows:
        blockers = _values(row.get("blockers"))
        row["readiness"] = "blocked" if blockers else ("incomplete" if row.get("owner") in {None, "", "owner-required"} else "ready")
    return rows


def _warnings(scenarios: list[dict[str, str]], paging: list[dict[str, str]], comms: list[dict[str, str]], criteria: list[dict[str, str]]) -> list[dict[str, str]]:
    warnings = []
    if not paging or any(not row.get("owner") for row in paging):
        warnings.append({"warning": "missing paging owner", "owner": "support_lead"})
    if not comms:
        warnings.append({"warning": "missing customer communication path", "owner": "communications_owner"})
    if not criteria:
        warnings.append({"warning": "missing success criteria", "owner": "support_lead"})
    return _numbered(warnings, "SED-W")


def _rows(value: Any, key: str, prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = {str(k): _text(v) for k, v in (item.items() if isinstance(item, dict) else [(key, item)]) if _text(v)}
        if row.get(key) or row.get("name"):
            row[key] = row.get(key) or row["name"]
            rows.append(row)
    return _numbered(sorted(rows, key=lambda row: row[key].casefold()), prefix)


def _evidence(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    refs = _values(plan.get("evidence_links") or plan.get("evidence_references") or spec.get("evidence_links"))
    return [{"id": f"SED-E{index:03d}", "reference": ref} for index, ref in enumerate(sorted(dict.fromkeys(refs), key=str.casefold), start=1)]


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
