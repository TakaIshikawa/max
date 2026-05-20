"""Generate deterministic customer migration readiness plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-customer-migration-readiness-plan/v1"
KIND = "max.spec.customer_migration_readiness_plan"
STATUS_ORDER = {"blocked": 0, "at-risk": 1, "ready": 2}


def generate_customer_migration_readiness_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    rows = _customer_rows(spec)
    gaps = _readiness_gaps(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "customer_count": len(rows),
            "blocked_count": sum(1 for row in rows if row["readiness"] == "blocked"),
            "at_risk_count": sum(1 for row in rows if row["readiness"] == "at-risk"),
            "ready_count": sum(1 for row in rows if row["readiness"] == "ready"),
        },
        "customer_rows": rows,
        "readiness_gaps": gaps,
        "migration_waves": _migration_waves(spec, rows),
        "rollback_contacts": _rollback_contacts(spec, rows),
    }


def render_customer_migration_readiness_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_customer_migration_readiness_plan(plan_or_spec)
    lines = ["# Customer Migration Readiness Plan", "", f"Schema version: {plan['schema_version']}", "", "## Customer Readiness", ""]
    for row in plan["customer_rows"]:
        lines.append(f"- {row['id']}: {row['customer']} readiness={row['readiness']} owner={row['owner']} wave={row['wave']} value={row['value_tier']}")
    lines.extend(["", "## Readiness Gaps", ""])
    if plan["readiness_gaps"]:
        for gap in plan["readiness_gaps"]:
            lines.append(f"- {gap['customer_id']}: {gap['gap']} owner={gap['owner']}")
    else:
        lines.append("- No readiness gaps identified.")
    lines.extend(["", "## Migration Waves", ""])
    for wave in plan["migration_waves"]:
        lines.append(f"- {wave['id']}: {wave['wave']} date={wave['date']} customers={', '.join(wave['customers'])}")
    lines.extend(["", "## Rollback Contacts", ""])
    for contact in plan["rollback_contacts"]:
        lines.append(f"- {contact['customer_id']}: {contact['contact']}")
    return "\n".join(lines).rstrip() + "\n"


def _customer_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(_raw_customers(spec), start=1):
        customer = _text(raw.get("customer") or raw.get("account") or raw.get("name")) or f"customer-{index}"
        blockers = _values(raw.get("blockers"), [])
        owner = _text(raw.get("owner"))
        comms = _text(raw.get("comms_status") or raw.get("communications_status") or raw.get("comms"))
        success = _values(raw.get("success_criteria"), [])
        readiness = _readiness(blockers, owner, comms, success)
        rows.append({"id": "", "customer": customer, "owner": owner or "migration_owner_required", "integrations": _values(raw.get("integrations"), []), "comms_status": comms or "missing", "success_criteria": success, "blockers": blockers, "wave": _text(raw.get("wave") or raw.get("migration_wave")) or "wave-unassigned", "value_tier": _text(raw.get("value_tier") or raw.get("tier")) or "standard", "readiness": readiness, "rollback_contact": _text(raw.get("rollback_contact")) or "rollback-contact-required"})
    if not rows:
        rows.append({"id": "", "customer": "customer-intake", "owner": "migration_owner_required", "integrations": [], "comms_status": "missing", "success_criteria": [], "blockers": ["migration scope required"], "wave": "wave-unassigned", "value_tier": "standard", "readiness": "blocked", "rollback_contact": "rollback-contact-required"})
    rows = sorted(rows, key=lambda row: (STATUS_ORDER[row["readiness"]], row["value_tier"] != "high", row["wave"].casefold(), row["customer"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"CMR-{index:03d}"
    return rows


def _readiness(blockers: list[str], owner: str, comms: str, success: list[str]) -> str:
    if blockers:
        return "blocked"
    if not owner or comms.casefold() not in {"sent", "ready", "complete", "completed"} or not success:
        return "at-risk"
    return "ready"


def _readiness_gaps(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    gaps = []
    for row in rows:
        for blocker in row["blockers"]:
            gaps.append({"customer_id": row["id"], "customer": row["customer"], "gap": f"blocker: {blocker}", "owner": row["owner"]})
        if row["owner"] == "migration_owner_required":
            gaps.append({"customer_id": row["id"], "customer": row["customer"], "gap": "missing migration owner", "owner": "migration_lead"})
        if row["comms_status"] == "missing":
            gaps.append({"customer_id": row["id"], "customer": row["customer"], "gap": "missing customer communications", "owner": row["owner"]})
        if not row["success_criteria"]:
            gaps.append({"customer_id": row["id"], "customer": row["customer"], "gap": "incomplete success criteria", "owner": row["owner"]})
    return gaps


def _migration_waves(spec: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_waves = _raw_items(spec, "migration_waves", "customer_migration_readiness")
    waves: dict[str, dict[str, Any]] = {}
    for raw in raw_waves:
        name = _text(raw.get("wave") or raw.get("name")) or "wave-unassigned"
        waves[name] = {"id": "", "wave": name, "date": _text(raw.get("date")) or "date-required", "customers": []}
    for row in rows:
        wave = waves.setdefault(row["wave"], {"id": "", "wave": row["wave"], "date": "date-required", "customers": []})
        wave["customers"].append(row["customer"])
    result = sorted(waves.values(), key=lambda wave: (_date_key(wave["date"]), wave["wave"].casefold()))
    for index, wave in enumerate(result, start=1):
        wave["id"] = f"CMW-{index:03d}"
        wave["customers"] = sorted(wave["customers"], key=str.casefold)
    return result


def _rollback_contacts(spec: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"customer_id": row["id"], "customer": row["customer"], "contact": row["rollback_contact"]} for row in rows]


def _raw_customers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return _raw_items(spec, "customers", "customer_migration_readiness") or _raw_items(spec, "accounts", "customer_migration_readiness")


def _raw_items(spec: dict[str, Any], key: str, nested: str) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get(nested) or spec.get(nested))
    candidates = plan.get(key) or metadata.get(key) or spec.get(key)
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "customer_rows" in value


def _date_key(value: str) -> tuple[int, str]:
    return (1, value.casefold()) if value == "date-required" else (0, value.casefold())


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
