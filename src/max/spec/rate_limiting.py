"""Generate deterministic rate limiting configurations for spec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


RATE_LIMITING_SCHEMA_VERSION = "max-rate-limiting/v1"

RATE_LIMITING_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "source_idea_id",
    "rate_limit_id",
    "rate_limit_type",
    "threshold",
    "time_window",
    "enforcement_strategy",
    "exemptions",
    "scope",
    "priority",
    "notes",
    "source_fields",
)


def generate_rate_limiting_config(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic rate limiting configuration."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source")
    source = source if isinstance(source, dict) else {}
    project = spec.get("project")
    project = project if isinstance(project, dict) else {}
    solution = spec.get("solution")
    solution = solution if isinstance(solution, dict) else {}
    execution = spec.get("execution")
    execution = execution if isinstance(execution, dict) else {}

    rate_limits = _rate_limit_records(spec, project, solution, execution)
    rate_limits = _prioritize_rate_limits(rate_limits)

    return {
        "schema_version": RATE_LIMITING_SCHEMA_VERSION,
        "kind": "max.rate_limiting_config",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": _compact(project.get("title"))
            or _compact(source.get("idea_id"))
            or "Untitled TactSpec",
            "rate_limit_count": len(rate_limits),
            "critical_limit_count": sum(1 for item in rate_limits if item["priority"] == "critical"),
            "high_limit_count": sum(1 for item in rate_limits if item["priority"] == "high"),
        },
        "rate_limits": rate_limits,
    }


def render_rate_limiting_config_csv(config: dict[str, Any]) -> str:
    """Render rate limiting configuration as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(RATE_LIMITING_CSV_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(config or {}):
        writer.writerow(row)  # type: ignore[arg-type]
    return output.getvalue()


def _rate_limit_records(
    spec: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    # Default rate limits for API endpoints
    endpoints = _get_endpoints(spec, solution)
    if endpoints:
        records.append(
            _rate_limit(
                rate_limit_type="api_endpoint",
                threshold=100,
                time_window="1 minute",
                enforcement_strategy="sliding_window",
                exemptions=None,
                scope="per_user",
                priority="high",
                notes="Standard API endpoint rate limit per user.",
                source_fields=["endpoints", "solution.technical_approach"],
            )
        )
        records.append(
            _rate_limit(
                rate_limit_type="api_endpoint_global",
                threshold=1000,
                time_window="1 minute",
                enforcement_strategy="sliding_window",
                exemptions=None,
                scope="global",
                priority="critical",
                notes="Global API rate limit across all users.",
                source_fields=["endpoints", "solution.technical_approach"],
            )
        )

    # Rate limits for authentication
    if _has_authentication(spec, solution):
        records.append(
            _rate_limit(
                rate_limit_type="authentication",
                threshold=5,
                time_window="15 minutes",
                enforcement_strategy="fixed_window",
                exemptions=None,
                scope="per_ip",
                priority="critical",
                notes="Login attempt rate limit to prevent brute force attacks.",
                source_fields=["security.auth", "solution.technical_approach"],
            )
        )

    # Rate limits for data operations
    if _has_data_operations(spec, solution):
        records.append(
            _rate_limit(
                rate_limit_type="data_mutation",
                threshold=50,
                time_window="1 minute",
                enforcement_strategy="token_bucket",
                exemptions="admin_users",
                scope="per_user",
                priority="high",
                notes="Rate limit for write operations to prevent abuse.",
                source_fields=["data_model", "execution.mvp_scope"],
            )
        )

    # Rate limits for external integrations
    integrations = _get_integrations(spec, solution)
    if integrations:
        records.append(
            _rate_limit(
                rate_limit_type="external_integration",
                threshold=20,
                time_window="1 minute",
                enforcement_strategy="leaky_bucket",
                exemptions=None,
                scope="per_integration",
                priority="high",
                notes="Rate limit for outbound calls to external services.",
                source_fields=["integrations", "solution.composability_notes"],
            )
        )

    # Fallback rate limit if no specific limits identified
    if not records:
        records.append(
            _rate_limit(
                rate_limit_type="default",
                threshold=100,
                time_window="1 minute",
                enforcement_strategy="sliding_window",
                exemptions=None,
                scope="global",
                priority="medium",
                notes="Conservative default rate limit when explicit requirements are not specified.",
                source_fields=["project.workflow_context", "execution.mvp_scope"],
            )
        )

    return records


def _rate_limit(
    *,
    rate_limit_type: str,
    threshold: int,
    time_window: str,
    enforcement_strategy: str,
    exemptions: str | None,
    scope: str,
    priority: str,
    notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": "",
        "type": rate_limit_type,
        "threshold": threshold,
        "time_window": time_window,
        "enforcement_strategy": enforcement_strategy,
        "exemptions": exemptions,
        "scope": scope,
        "priority": priority,
        "notes": _compact(notes),
        "source_fields": [field for field in source_fields if field],
    }


def _prioritize_rate_limits(rate_limits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rate_limits,
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item["priority"], 4),
            item["type"],
        ),
    )
    return [{**item, "id": f"RL{index:02d}"} for index, item in enumerate(ordered, start=1)]


def _get_endpoints(spec: dict[str, Any], solution: dict[str, Any]) -> list[Any]:
    endpoints: list[Any] = []
    for key in ("endpoints", "routes", "apis", "api_endpoints"):
        value = spec.get(key)
        if value:
            endpoints.extend(_list(value))
        value = solution.get(key)
        if value:
            endpoints.extend(_list(value))
    return [item for item in endpoints if item]


def _has_authentication(spec: dict[str, Any], solution: dict[str, Any]) -> bool:
    for text in [
        _compact(spec.get("security", {}).get("auth")) if isinstance(spec.get("security"), dict) else "",
        _compact(solution.get("technical_approach")),
        _compact(solution.get("composability_notes")),
    ]:
        if any(term in text.lower() for term in ("auth", "login", "oauth", "credential")):
            return True
    return False


def _has_data_operations(spec: dict[str, Any], solution: dict[str, Any]) -> bool:
    has_data_model = bool(
        spec.get("data_model")
        or solution.get("data_model")
        or solution.get("schemas")
        or solution.get("entities")
    )
    return has_data_model


def _get_integrations(spec: dict[str, Any], solution: dict[str, Any]) -> list[Any]:
    integrations: list[Any] = []
    for key in ("integrations", "external_services", "dependencies", "webhooks"):
        value = spec.get(key)
        if value:
            integrations.extend(_list(value))
        value = solution.get(key)
        if value:
            integrations.extend(_list(value))
    return [item for item in integrations if item]


def _csv_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    rate_limits = config.get("rate_limits")
    if not isinstance(rate_limits, list):
        return []
    return [_csv_row(config, item) for item in rate_limits if isinstance(item, dict)]


def _csv_row(config: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    source = config.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "schema_version": _csv_cell(config.get("schema_version")),
        "kind": _csv_cell(config.get("kind")),
        "source_idea_id": _csv_cell(source.get("idea_id")),
        "rate_limit_id": _csv_cell(item.get("id")),
        "rate_limit_type": _csv_cell(item.get("type")),
        "threshold": _csv_cell(item.get("threshold")),
        "time_window": _csv_cell(item.get("time_window")),
        "enforcement_strategy": _csv_cell(item.get("enforcement_strategy")),
        "exemptions": _csv_cell(item.get("exemptions")),
        "scope": _csv_cell(item.get("scope")),
        "priority": _csv_cell(item.get("priority")),
        "notes": _csv_cell(item.get("notes")),
        "source_fields": _csv_cell(item.get("source_fields")),
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_cell(key)}={_csv_cell(item)}"
            for key, item in sorted(value.items())
            if _csv_cell(item)
        )
    if isinstance(value, (list, tuple, set)):
        return " | ".join(_csv_cell(item) for item in _list(value) if _csv_cell(item))
    return _compact(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
