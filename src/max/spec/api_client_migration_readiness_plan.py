"""Generate deterministic API client migration readiness plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-api-client-migration-readiness-plan/v1"
KIND = "max.spec.api_client_migration_readiness_plan"
STATUS_ORDER = {"blocked": 0, "at-risk": 1, "ready": 2}


def generate_api_client_migration_readiness_plan(spec_like: Any) -> dict[str, Any]:
    spec = _dict(spec_like)
    plan = _nested(spec, "api_client_migration_readiness")
    cohorts = _cohorts(plan, spec)
    endpoints = _rows(plan.get("deprecated_endpoints") or spec.get("deprecated_endpoints"), "endpoint", "ACM-E")
    sdks = _rows(plan.get("sdk_requirements") or spec.get("sdk_requirements"), "sdk", "ACM-S")
    guides = _rows(plan.get("migration_guidance") or plan.get("migration_guides") or spec.get("migration_guidance"), "guide", "ACM-G")
    deadlines = _rows(plan.get("deadlines") or spec.get("deadlines"), "deadline", "ACM-D")
    owners = _rows(plan.get("owners") or spec.get("owners"), "owner", "ACM-O")
    checks = _rows(plan.get("validation_checks") or spec.get("validation_checks"), "check", "ACM-V")
    blockers = _blockers(cohorts)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "ready_count": sum(1 for row in cohorts if row["readiness"] == "ready"),
            "at_risk_count": sum(1 for row in cohorts if row["readiness"] == "at-risk"),
            "blocked_count": sum(1 for row in cohorts if row["readiness"] == "blocked"),
        },
        "client_cohorts": cohorts,
        "deprecated_endpoints": endpoints,
        "sdk_requirements": sdks,
        "migration_guidance": guides,
        "deadlines": deadlines,
        "owners": owners,
        "validation_checks": checks,
        "blockers": blockers,
    }


def render_api_client_migration_readiness_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if isinstance(plan_or_spec, dict) and plan_or_spec.get("kind") == KIND else generate_api_client_migration_readiness_plan(plan_or_spec)
    lines = ["# API Client Migration Readiness Plan", ""]
    for title, key, label in (("Client Cohorts", "client_cohorts", "cohort"), ("Deprecated Endpoints", "deprecated_endpoints", "endpoint"), ("SDK Requirements", "sdk_requirements", "sdk"), ("Migration Guidance", "migration_guidance", "guide"), ("Validation Checks", "validation_checks", "check"), ("Blockers", "blockers", "blocker")):
        _section(lines, title, plan[key], label)
    return "\n".join(lines).rstrip() + "\n"


def _cohorts(plan: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    rows = _rows(plan.get("client_cohorts") or plan.get("cohorts") or spec.get("client_cohorts"), "cohort", "ACM-C")
    if not rows:
        rows = [{"id": "ACM-C001", "cohort": "client-cohort-required"}]
    for row in rows:
        deadline = row.get("deadline", "")
        expired = bool(deadline and deadline < "2026-05-21")
        missing_guide = not row.get("migration_guide") and not row.get("guide")
        missing_owner = not row.get("owner")
        row["readiness"] = "blocked" if expired or missing_owner else ("at-risk" if missing_guide else "ready")
        row["risk_reason"] = "; ".join(reason for reason, active in (("expired deadline", expired), ("missing migration guide", missing_guide), ("unassigned owner", missing_owner)) if active) or "ready"
    rows = sorted(rows, key=lambda row: (STATUS_ORDER[row["readiness"]], row["cohort"].casefold()))
    return _numbered(rows, "ACM-C")


def _blockers(cohorts: list[dict[str, str]]) -> list[dict[str, str]]:
    blockers = []
    for row in cohorts:
        for reason in row["risk_reason"].split("; "):
            if reason != "ready":
                blockers.append({"cohort": row["cohort"], "blocker": reason, "owner": row.get("owner") or "migration_owner"})
    return _numbered(blockers, "ACM-B")


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


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
