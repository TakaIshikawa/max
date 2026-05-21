"""Generate deterministic payment processor cutover readiness plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-payment-processor-cutover-plan/v1"
KIND = "max.spec.payment_processor_cutover_plan"


def generate_payment_processor_cutover_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "payment_processor_cutover")
    providers = _providers(spec, plan)
    windows = _windows(spec, plan, providers)
    checks = _checks(spec, plan, providers)
    triggers = _triggers(spec, plan, providers)
    owners = _owners(spec, plan, providers)
    evidence = _evidence(spec, plan)
    warnings = _warnings(providers, checks, triggers, owners, evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "provider_count": len(providers),
            "cutover_window_count": len(windows),
            "reconciliation_check_count": len(checks),
            "rollback_trigger_count": len(triggers),
            "warning_count": len(warnings),
            "readiness": "blocked" if warnings else "ready",
        },
        "payment_providers": providers,
        "cutover_steps": windows,
        "reconciliation_checks": checks,
        "rollback_triggers": triggers,
        "owner_assignments": owners,
        "evidence_references": evidence,
        "readiness_warnings": warnings,
    }


def render_payment_processor_cutover_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_payment_processor_cutover_plan(plan_or_spec)
    lines = ["# Payment Processor Cutover Plan", "", f"Schema version: {plan['schema_version']}", ""]
    _section(lines, "Payment Providers", plan["payment_providers"], lambda row: f"- {row['id']}: {row['name']} role={row['role']} status={row['status']}")
    _section(lines, "Cutover Steps", plan["cutover_steps"], lambda row: f"- {row['id']}: {row['provider']} window={row['window']} step={row['step']}")
    _section(lines, "Reconciliation Checks", plan["reconciliation_checks"], lambda row: f"- {row['id']}: {row['provider']} {row['check']} evidence={row['evidence']}")
    _section(lines, "Rollback Criteria", plan["rollback_triggers"], lambda row: f"- {row['id']}: {row['provider']} trigger={row['trigger']} criteria={row['criteria']} owner={row['owner']}")
    _section(lines, "Owner Assignments", plan["owner_assignments"], lambda row: f"- {row['id']}: {row['provider']} {row['role']}={row['owner']}")
    _section(lines, "Readiness Warnings", plan["readiness_warnings"], lambda row: f"- {row['id']}: {row['provider']} {row['warning']}")
    return "\n".join(lines).rstrip() + "\n"


def _providers(spec: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(plan.get("providers") or spec.get("payment_providers") or spec.get("providers"), "name")
    if not rows:
        rows = [{"name": "payment-processor-required"}]
    result = []
    for row in rows:
        result.append({
            "id": "",
            "name": row["name"],
            "role": _text(row.get("role")) or _text(row.get("mode")) or "processor",
            "status": _text(row.get("status")) or "pending",
            "traffic_share": _text(row.get("traffic_share")) or _text(row.get("share")) or "not specified",
        })
    return _numbered(sorted(_dedupe(result, "name"), key=lambda row: row["name"].casefold()), "PPC-P")


def _windows(spec: dict[str, Any], plan: dict[str, Any], providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _records(plan.get("cutover_windows") or plan.get("cutover_steps") or spec.get("cutover_windows"), "step")
    if not rows:
        rows = [{"provider": provider["name"], "step": "switch payment traffic", "window": "window-required"} for provider in providers]
    result = [{
        "id": "",
        "provider": _text(row.get("provider")) or providers[0]["name"],
        "window": _text(row.get("window")) or _text(row.get("time")) or "window-required",
        "step": row["step"],
        "sequence": _text(row.get("sequence")) or str(index),
    } for index, row in enumerate(rows, start=1)]
    return _numbered(sorted(result, key=lambda row: (row["provider"].casefold(), row["sequence"], row["step"].casefold())), "PPC-S")


def _checks(spec: dict[str, Any], plan: dict[str, Any], providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _records(plan.get("reconciliation_checks") or spec.get("reconciliation_checks"), "check")
    result = [{
        "id": "",
        "provider": _text(row.get("provider")) or providers[0]["name"],
        "check": row["check"],
        "threshold": _text(row.get("threshold")) or "zero unreconciled critical transactions",
        "evidence": _text(row.get("evidence") or row.get("evidence_ref")) or "evidence-required",
        "owner": _text(row.get("owner")) or "reconciliation_owner_required",
    } for row in rows]
    return _numbered(sorted(result, key=lambda row: (row["provider"].casefold(), row["check"].casefold())), "PPC-R")


def _triggers(spec: dict[str, Any], plan: dict[str, Any], providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _records(plan.get("rollback_triggers") or spec.get("rollback_triggers"), "trigger")
    result = [{
        "id": "",
        "provider": _text(row.get("provider")) or providers[0]["name"],
        "trigger": row["trigger"],
        "criteria": _text(row.get("criteria") or row.get("threshold")) or "material payment failure or reconciliation mismatch",
        "owner": _text(row.get("owner")) or "rollback_owner_required",
    } for row in rows]
    return _numbered(sorted(result, key=lambda row: (row["provider"].casefold(), row["trigger"].casefold())), "PPC-B")


def _owners(spec: dict[str, Any], plan: dict[str, Any], providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _records(plan.get("owners") or plan.get("owner_assignments") or spec.get("owners"), "role")
    if not rows:
        rows = [{"provider": provider["name"], "role": "cutover_owner"} for provider in providers]
    result = [{
        "id": "",
        "provider": _text(row.get("provider")) or providers[0]["name"],
        "role": row["role"],
        "owner": _text(row.get("owner")) or "owner-required",
        "responsibility": _text(row.get("responsibility")) or "Own assigned payment cutover control.",
    } for row in rows]
    return _numbered(sorted(result, key=lambda row: (row["provider"].casefold(), row["role"].casefold())), "PPC-O")


def _warnings(providers: list[dict[str, Any]], checks: list[dict[str, Any]], triggers: list[dict[str, Any]], owners: list[dict[str, Any]], evidence: list[dict[str, str]]) -> list[dict[str, str]]:
    warnings = []
    for provider in providers:
        name = provider["name"]
        if not any(row["provider"] == name and row["owner"] != "owner-required" for row in owners):
            warnings.append({"id": "", "provider": name, "warning": "missing owner assignment", "severity": "high"})
        provider_checks = [row for row in checks if row["provider"] == name]
        if not provider_checks or any(row["evidence"] == "evidence-required" for row in provider_checks):
            warnings.append({"id": "", "provider": name, "warning": "missing reconciliation evidence", "severity": "high"})
        if not any(row["provider"] == name for row in triggers):
            warnings.append({"id": "", "provider": name, "warning": "missing rollback trigger", "severity": "critical"})
    if not evidence:
        warnings.append({"id": "", "provider": "all", "warning": "missing evidence references", "severity": "medium"})
    return _numbered(warnings, "PPC-W")


def _evidence(spec: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, str]]:
    refs = _values(plan.get("evidence_references") or spec.get("evidence_references") or spec.get("evidence"))
    return [{"id": f"PPC-E{index}", "reference": ref} for index, ref in enumerate(sorted(dict.fromkeys(refs), key=str.casefold), start=1)]


def _section(lines: list[str], title: str, rows: list[dict[str, Any]], render: Any) -> None:
    lines.extend([f"## {title}", ""])
    lines.extend(render(row) for row in rows)
    if not rows:
        lines.append("- None.")
    lines.append("")


def _is_plan(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND


def _nested(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    return _dict(spec.get(key) or metadata.get(key))


def _records(value: Any, default_key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = dict(item) if isinstance(item, dict) else {default_key: item}
        label = _text(row.get(default_key) or row.get("name"))
        if label:
            row[default_key] = label
            rows.append(row)
    return rows


def _numbered(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    for index, row in enumerate(rows, start=1):
        row["id"] = f"{prefix}{index:03d}"
    return rows


def _dedupe(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        marker = row[key].casefold()
        if marker not in seen:
            seen.add(marker)
            result.append(row)
    return result


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _values(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("references") or value.get("refs") or value.get("ids")
    values = value if isinstance(value, list) else [value]
    return [_text(item) for item in values if _text(item)]


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
