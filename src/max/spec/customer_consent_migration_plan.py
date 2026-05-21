"""Generate deterministic customer consent migration plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-customer-consent-migration-plan/v1"
KIND = "max.spec.customer_consent_migration_plan"


def generate_customer_consent_migration_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "customer_consent_migration")
    categories = _rows(plan.get("consent_categories") or spec.get("consent_categories"), "category", "CCM-C")
    if not categories:
        categories = [{"id": "CCM-C001", "category": "consent-category-required", "basis": "basis-required", "status": "pending"}]
    cohorts = _cohorts(plan, spec)
    rules = _rules(plan, spec, categories)
    communications = _communications(plan, spec, cohorts)
    fallbacks = _fallbacks(plan, spec, categories)
    checks = _checks(plan, spec, categories)
    evidence = _evidence(plan, spec)
    warnings = _warnings(categories, communications, fallbacks, checks, evidence, plan, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "category_count": len(categories),
            "cohort_count": len(cohorts),
            "migration_rule_count": len(rules),
            "warning_count": len(warnings),
            "readiness": "blocked" if warnings else "ready",
        },
        "consent_categories": categories,
        "impacted_cohorts": cohorts,
        "migration_rules": rules,
        "legal_review": {"status": _text(plan.get("legal_review") or spec.get("legal_review")) or "missing"},
        "communications": communications,
        "fallback_paths": fallbacks,
        "verification_checks": checks,
        "evidence_references": evidence,
        "readiness_warnings": warnings,
    }


def render_customer_consent_migration_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if isinstance(plan_or_spec, dict) and plan_or_spec.get("kind") == KIND else generate_customer_consent_migration_plan(plan_or_spec)
    lines = ["# Customer Consent Migration Plan", ""]
    _section(lines, "Consent Categories", plan["consent_categories"], "category")
    _section(lines, "Impacted Cohorts", plan["impacted_cohorts"], "cohort")
    _section(lines, "Migration Rules", plan["migration_rules"], "rule")
    _section(lines, "Communications", plan["communications"], "channel")
    _section(lines, "Fallback Paths", plan["fallback_paths"], "path")
    _section(lines, "Verification Checks", plan["verification_checks"], "check")
    _section(lines, "Warnings", plan["readiness_warnings"], "warning")
    return "\n".join(lines).rstrip() + "\n"


def _cohorts(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = _rows(plan.get("impacted_cohorts") or plan.get("cohorts") or spec.get("impacted_cohorts"), "cohort", "CCM-H")
    return rows or [{"id": "CCM-H001", "cohort": "customer-cohort-required", "region": "all", "impact": "consent migration scope required"}]


def _rules(plan: dict[str, Any], spec: dict[str, Any], categories: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = _rows(plan.get("migration_rules") or spec.get("migration_rules"), "rule", "CCM-R")
    return rows or _numbered([{"category": row["category"], "rule": "preserve existing opt-in state", "owner": "privacy_owner"} for row in categories], "CCM-R")


def _communications(plan: dict[str, Any], spec: dict[str, Any], cohorts: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = _rows(plan.get("communications") or plan.get("communication_steps") or spec.get("communications"), "channel", "CCM-M")
    return rows or _numbered([{"cohort": row["cohort"], "channel": "communication-required", "timing": "before migration"} for row in cohorts], "CCM-M")


def _fallbacks(plan: dict[str, Any], spec: dict[str, Any], categories: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = _rows(plan.get("fallback_paths") or plan.get("fallback_handling") or spec.get("fallback_paths"), "path", "CCM-F")
    return rows or _numbered([{"category": row["category"], "path": "restore prior consent state", "opt_out_verified": "false"} for row in categories], "CCM-F")


def _checks(plan: dict[str, Any], spec: dict[str, Any], categories: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = _rows(plan.get("verification_checks") or spec.get("verification_checks"), "check", "CCM-V")
    return rows or _numbered([{"category": row["category"], "check": "verify migrated consent and opt-out handling", "evidence": "evidence-required"} for row in categories], "CCM-V")


def _warnings(categories: list[dict[str, str]], communications: list[dict[str, str]], fallbacks: list[dict[str, str]], checks: list[dict[str, str]], evidence: list[dict[str, str]], plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    warnings = []
    legal = _text(plan.get("legal_review") or spec.get("legal_review")).casefold()
    if legal not in {"approved", "complete", "completed"}:
        warnings.append({"warning": "missing legal approval", "owner": "privacy_legal"})
    if any(row.get("channel") == "communication-required" for row in communications):
        warnings.append({"warning": "missing customer communication", "owner": "communications_owner"})
    if any(_text(row.get("opt_out_verified")).casefold() not in {"true", "yes", "verified"} for row in fallbacks):
        warnings.append({"warning": "unverified opt-out handling", "owner": "privacy_owner"})
    if any(row.get("evidence") == "evidence-required" for row in checks) or not evidence:
        warnings.append({"warning": "missing verification evidence", "owner": "privacy_owner"})
    return _numbered(warnings, "CCM-W")


def _evidence(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    refs = _values(plan.get("evidence_references") or spec.get("evidence_references"))
    return [{"id": f"CCM-E{index:03d}", "reference": ref} for index, ref in enumerate(sorted(dict.fromkeys(refs), key=str.casefold), start=1)]


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


def _section(lines: list[str], title: str, rows: list[dict[str, str]], label: str) -> None:
    lines.extend([f"## {title}", ""])
    for row in rows:
        detail = ", ".join(f"{key}={value}" for key, value in row.items() if key != "id")
        lines.append(f"- {row['id']}: {row.get(label) or detail}")
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
