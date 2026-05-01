"""Generate deterministic dependency inventories for buildable ideas."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


DEPENDENCY_INVENTORY_SCHEMA_VERSION = "max-dependency-inventory/v1"

_DATA_KEYS = {"cache", "data", "database", "db", "queue", "search", "storage", "warehouse"}
_EXTERNAL_KEYS = {"ai", "analytics", "auth", "billing", "cloud", "crm", "email", "hosting", "payments"}
_INTEGRATION_KEYS = {"automation", "ci", "messaging", "notification", "notifications", "webhook"}

_KNOWN_DEPENDENCIES = {
    "aws": ("external_service", "AWS"),
    "azure": ("external_service", "Azure"),
    "datadog": ("external_service", "Datadog"),
    "fastapi": ("runtime", "FastAPI"),
    "github": ("integration", "GitHub"),
    "gitlab": ("integration", "GitLab"),
    "google": ("external_service", "Google"),
    "hubspot": ("external_service", "HubSpot"),
    "jira": ("integration", "Jira"),
    "mongodb": ("data_store", "MongoDB"),
    "mysql": ("data_store", "MySQL"),
    "node": ("runtime", "Node.js"),
    "oauth": ("external_service", "OAuth"),
    "openai": ("external_service", "OpenAI"),
    "postgres": ("data_store", "Postgres"),
    "postgresql": ("data_store", "Postgres"),
    "python": ("runtime", "Python"),
    "redis": ("data_store", "Redis"),
    "s3": ("data_store", "S3"),
    "salesforce": ("external_service", "Salesforce"),
    "slack": ("integration", "Slack"),
    "stripe": ("external_service", "Stripe"),
    "supabase": ("data_store", "Supabase"),
    "teams": ("integration", "Teams"),
    "trello": ("integration", "Trello"),
    "twilio": ("external_service", "Twilio"),
    "typescript": ("runtime", "TypeScript"),
    "webhook": ("integration", "Webhook"),
}

_HIGH_RISK_TERMS = {
    "credential",
    "gdpr",
    "hipaa",
    "oauth",
    "patient",
    "payment",
    "pii",
    "privacy",
    "regulated",
    "secret",
    "token",
}
_MEDIUM_RISK_TERMS = {
    "api",
    "auth",
    "backup",
    "customer",
    "email",
    "external",
    "integration",
    "log",
    "retention",
    "webhook",
}


def generate_dependency_inventory(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready dependency inventory from an idea and optional spec preview."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    dependencies = _dependency_records(unit, spec)
    dependencies = _dedupe_dependencies(dependencies)
    dependencies = _with_risk_links(dependencies, unit, spec)
    dependencies = _fallback_dependencies(dependencies, unit, spec)
    dependencies = _prioritize_dependencies(dependencies)
    mitigation_actions = _mitigation_actions(dependencies, unit, evaluation, spec)
    missing_input_notes = _missing_input_notes(unit, spec)

    return {
        "schema_version": DEPENDENCY_INVENTORY_SCHEMA_VERSION,
        "kind": "max.dependency_inventory",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": str(unit.category),
            "evaluation_available": evaluation is not None,
            "tact_spec_available": bool(spec),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": unit.title,
            "dependency_count": len(dependencies),
            "data_store_count": _count_type(dependencies, "data_store"),
            "external_service_count": _count_type(dependencies, "external_service"),
            "integration_count": _count_type(dependencies, "integration"),
            "runtime_count": _count_type(dependencies, "runtime"),
            "high_risk_count": sum(1 for item in dependencies if item["risk_level"] == "high"),
            "missing_input_note_count": len(missing_input_notes),
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
        },
        "dependencies": dependencies,
        "mitigation_actions": mitigation_actions,
        "missing_input_notes": missing_input_notes,
    }


def render_dependency_inventory_markdown(inventory: dict[str, Any]) -> str:
    """Render a generated dependency inventory as stable markdown."""
    source = inventory.get("source", {})
    summary = inventory.get("summary", {})
    title = _text(summary.get("title")) or _text(inventory.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Dependency Inventory",
        "",
        f"- Schema version: {_text(inventory.get('schema_version'))}",
        f"- Idea ID: {_text(inventory.get('idea_id'))}",
        f"- Source status: {_text(source.get('status'))}",
        f"- Domain: {_text(source.get('domain'))}",
        f"- Category: {_text(source.get('category'))}",
        f"- Dependency count: {_text(summary.get('dependency_count'))}",
        f"- Data stores: {_text(summary.get('data_store_count'))}",
        f"- External services: {_text(summary.get('external_service_count'))}",
        f"- Integrations: {_text(summary.get('integration_count'))}",
        f"- High-risk dependencies: {_text(summary.get('high_risk_count'))}",
        "",
        "## Dependencies",
        "",
    ]

    dependencies = inventory.get("dependencies") or []
    if dependencies:
        for item in dependencies:
            lines.extend(
                [
                    f"### {item.get('id')}: {_text(item.get('name'))}",
                    "",
                    f"- Type: {_text(item.get('type'))}",
                    f"- Owner: {_text(item.get('owner'))}",
                    f"- Risk level: {_text(item.get('risk_level'))}",
                    f"- Source fields: {_inline_list(item.get('source_fields') or [])}",
                    f"- Notes: {_text(item.get('notes'))}",
                    "",
                ]
            )
    else:
        lines.extend(["No dependencies identified.", ""])

    lines.extend(["## Mitigation Actions", ""])
    lines.extend(_bullets(inventory.get("mitigation_actions") or [], empty="None."))
    lines.extend(["", "## Missing Input Notes", ""])
    lines.extend(_bullets(inventory.get("missing_input_notes") or [], empty="None."))

    return "\n".join(lines).rstrip() + "\n"


def _dependency_records(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for field, stack in _stack_sources(unit, spec):
        for key, value in stack.items():
            for name in _values(value):
                dep_type, label = _classify_dependency(key, name)
                records.append(
                    _dependency(
                        name=label,
                        dep_type=dep_type,
                        source_fields=[field, f"{field}.{key}"],
                        notes=f"Suggested stack entry for {key}.",
                    )
                )

    for field, text in _text_sources(unit, spec):
        for token, (dep_type, label) in _KNOWN_DEPENDENCIES.items():
            if token in text.lower():
                records.append(
                    _dependency(
                        name=label,
                        dep_type=dep_type,
                        source_fields=[field],
                        notes="Detected in project or execution narrative.",
                    )
                )
    return records


def _with_risk_links(
    dependencies: list[dict[str, Any]], unit: BuildableUnit, spec: dict[str, Any]
) -> list[dict[str, Any]]:
    risks = _risk_texts(unit, spec)
    if not risks:
        return dependencies

    risk_text = " ".join(risks).lower()
    updated: list[dict[str, Any]] = []
    for item in dependencies:
        name = item["name"].lower()
        source_fields = list(item["source_fields"])
        risk_level = item["risk_level"]
        has_high_risk_term = any(term in risk_text for term in _HIGH_RISK_TERMS)
        risk_linked = name in risk_text or (item["type"] == "data_store" and has_high_risk_term)
        if risk_linked:
            source_fields.append("execution.risks")
            risk_level = "high" if has_high_risk_term else "medium"
        updated.append(
            {**item, "risk_level": risk_level, "source_fields": _dedupe_strings(source_fields)}
        )

    if any(term in risk_text for term in _MEDIUM_RISK_TERMS | _HIGH_RISK_TERMS):
        updated.append(
            _dependency(
                name="Risk review dependency",
                dep_type="risk_control",
                source_fields=["domain_risks", "execution.risks"],
                notes="Domain or execution risks require explicit owner review before build handoff.",
                risk_level="high" if any(term in risk_text for term in _HIGH_RISK_TERMS) else "medium",
            )
        )
    return updated


def _fallback_dependencies(
    dependencies: list[dict[str, Any]], unit: BuildableUnit, spec: dict[str, Any]
) -> list[dict[str, Any]]:
    if dependencies:
        return dependencies

    source_fields = ["suggested_stack"]
    if not unit.suggested_stack:
        source_fields.append("unit.suggested_stack")
    if not _spec_stack(spec):
        source_fields.append("tact_spec.solution.suggested_stack")

    return [
        _dependency(
            name="Implementation runtime",
            dep_type="runtime",
            source_fields=source_fields,
            notes="No explicit stack was provided; choose and record the runtime before estimation.",
            risk_level="medium",
        ),
        _dependency(
            name="Persistence boundary",
            dep_type="data_store",
            source_fields=["problem", "solution", "execution.mvp_scope"],
            notes="Sparse inputs do not prove whether data is transient or stored.",
            risk_level="medium",
        ),
    ]


def _mitigation_actions(
    dependencies: list[dict[str, Any]],
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[str]:
    actions = [
        "Assign an accountable owner for each dependency before implementation starts.",
        "Confirm service limits, credentials, and local development substitutes for external dependencies.",
    ]
    if any(item["type"] == "data_store" for item in dependencies):
        actions.append("Document data retention, backup, migration, and restore expectations for data stores.")
    if any(item["risk_level"] == "high" for item in dependencies):
        actions.append("Review high-risk dependencies with security, compliance, or domain owners before build handoff.")
    if evaluation is None:
        actions.append("Run utility evaluation before treating dependency risk as final.")
    if _missing_input_notes(unit, spec):
        actions.append("Resolve missing stack, integration, and data-flow inputs before estimating build effort.")
    return _dedupe_strings(actions)


def _missing_input_notes(unit: BuildableUnit, spec: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if not unit.suggested_stack and not _spec_stack(spec):
        notes.append("No suggested stack entries were provided; fallback dependencies are conservative placeholders.")
    if not _compact(unit.tech_approach) and not _spec_text(spec, ("solution", "technical_approach")):
        notes.append("No technical approach was provided; integration and runtime detection may be incomplete.")
    if not unit.domain_risks and not _list(_spec_get(spec, ("execution", "risks"))):
        notes.append("No risk fields were provided; dependency risk levels only reflect deterministic keyword detection.")
    return notes


def _dependency(
    *,
    name: str,
    dep_type: str,
    source_fields: list[str],
    notes: str,
    risk_level: str | None = None,
) -> dict[str, Any]:
    clean_name = _compact(name) or "Unspecified dependency"
    clean_type = dep_type if dep_type else "runtime"
    return {
        "id": "",
        "name": clean_name,
        "type": clean_type,
        "owner": _owner_for(clean_type),
        "risk_level": risk_level or _risk_level(clean_type, clean_name, notes),
        "source_fields": _dedupe_strings(source_fields),
        "notes": _compact(notes),
    }


def _prioritize_dependencies(dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        dependencies,
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["risk_level"], 3),
            item["type"],
            item["name"].lower(),
        ),
    )
    return [{**item, "id": f"DEP{index:02d}"} for index, item in enumerate(ordered, start=1)]


def _dedupe_dependencies(dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in dependencies:
        key = (item["type"], item["name"].lower())
        if key not in merged:
            merged[key] = {**item, "source_fields": list(item["source_fields"])}
            continue
        merged[key]["source_fields"] = _dedupe_strings(
            [*merged[key]["source_fields"], *item["source_fields"]]
        )
        if _risk_rank(item["risk_level"]) < _risk_rank(merged[key]["risk_level"]):
            merged[key]["risk_level"] = item["risk_level"]
    return list(merged.values())


def _classify_dependency(key: str, value: str) -> tuple[str, str]:
    key_lower = _compact(key).lower()
    value_text = _compact(value)
    value_lower = value_text.lower()
    for token, (dep_type, label) in _KNOWN_DEPENDENCIES.items():
        if token in value_lower:
            return dep_type, label
    if key_lower in _DATA_KEYS or any(term in value_lower for term in _DATA_KEYS):
        return "data_store", value_text
    if key_lower in _EXTERNAL_KEYS:
        return "external_service", value_text
    if key_lower in _INTEGRATION_KEYS or "api" in value_lower:
        return "integration", value_text
    return "runtime", value_text


def _risk_level(dep_type: str, name: str, notes: str) -> str:
    haystack = f"{dep_type} {name} {notes}".lower()
    if dep_type == "risk_control" or any(term in haystack for term in _HIGH_RISK_TERMS):
        return "high"
    if dep_type in {"data_store", "external_service", "integration"} or any(
        term in haystack for term in _MEDIUM_RISK_TERMS
    ):
        return "medium"
    return "low"


def _owner_for(dep_type: str) -> str:
    return {
        "data_store": "data_owner",
        "external_service": "platform_owner",
        "integration": "integration_owner",
        "risk_control": "product_owner",
        "runtime": "engineering_owner",
    }.get(dep_type, "engineering_owner")


def _stack_sources(unit: BuildableUnit, spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    sources: list[tuple[str, dict[str, Any]]] = []
    if isinstance(unit.suggested_stack, dict) and unit.suggested_stack:
        sources.append(("unit.suggested_stack", unit.suggested_stack))
    stack = _spec_stack(spec)
    if stack:
        sources.append(("tact_spec.solution.suggested_stack", stack))
    return sources


def _text_sources(unit: BuildableUnit, spec: dict[str, Any]) -> list[tuple[str, str]]:
    sources = [
        ("unit.solution", unit.solution),
        ("unit.tech_approach", unit.tech_approach),
        ("unit.composability_notes", unit.composability_notes),
        ("unit.validation_plan", unit.validation_plan),
        ("unit.workflow_context", unit.workflow_context),
    ]
    for path in (
        ("solution", "approach"),
        ("solution", "technical_approach"),
        ("solution", "composability_notes"),
        ("execution", "mvp_scope"),
        ("execution", "validation_plan"),
    ):
        value = _spec_get(spec, path)
        text = " ".join(_values(value)) if isinstance(value, list) else _compact(value)
        if text:
            sources.append((f"tact_spec.{'.'.join(path)}", text))
    return [(field, _compact(text)) for field, text in sources if _compact(text)]


def _risk_texts(unit: BuildableUnit, spec: dict[str, Any]) -> list[str]:
    return [
        *_values(unit.domain_risks),
        *_values(_spec_get(spec, ("execution", "risks"))),
        *_values(_spec_get(spec, ("evaluation", "weaknesses"))),
    ]


def _spec_stack(spec: dict[str, Any]) -> dict[str, Any]:
    value = _spec_get(spec, ("solution", "suggested_stack"))
    return value if isinstance(value, dict) else {}


def _spec_text(spec: dict[str, Any], path: tuple[str, ...]) -> str:
    return _compact(_spec_get(spec, path))


def _spec_get(spec: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = spec
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, dict):
        return [_compact(item) for item in value.values() if _compact(item)]
    if isinstance(value, (list, tuple, set)):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _count_type(dependencies: list[dict[str, Any]], dep_type: str) -> int:
    return sum(1 for item in dependencies if item["type"] == dep_type)


def _risk_rank(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 3)


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _bullets(items: list[Any], *, empty: str | None = None) -> list[str]:
    values = [f"- {_text(item)}" for item in items if _text(item)]
    if values:
        return values
    return [empty] if empty else []


def _inline_list(items: list[Any]) -> str:
    values = [_text(item) for item in items if _text(item)]
    return ", ".join(values) if values else "none"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
