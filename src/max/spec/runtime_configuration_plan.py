"""Generate deterministic runtime configuration plans for TactSpec previews."""

from __future__ import annotations

import csv
import re
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max-runtime-configuration-plan/v1"
KIND = "max.runtime_configuration_plan"

RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "title",
    "item_id",
    "name",
    "purpose",
    "owner",
    "required",
    "secret",
    "default_value",
    "environment",
    "validation",
    "rollback_default",
    "source_fields",
    "evidence_references",
    "notes",
)

_INTEGRATION_TERMS = {
    "Datadog": ("datadog",),
    "GitHub": ("github",),
    "HubSpot": ("hubspot",),
    "Jira": ("jira", "atlassian"),
    "Linear": ("linear",),
    "OpenAI": ("openai", "llm", "model provider"),
    "Salesforce": ("salesforce",),
    "Sentry": ("sentry",),
    "Slack": ("slack",),
    "Stripe": ("stripe",),
    "Teams": ("microsoft teams", "teams"),
    "Twilio": ("twilio",),
}


def generate_runtime_configuration_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic runtime configuration guidance."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    stack = solution.get("suggested_stack")

    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    workflow = _workflow(project)
    evidence_references = _evidence_references(spec)
    integrations = _integrations(spec, stack)
    config_items = _configuration_items(title, workflow, stack, integrations)
    feature_toggles = _feature_toggles(title, integrations, execution)
    secrets = _secrets(stack, integrations)
    operational_limits = _operational_limits(spec, execution, stack)
    validation_checks = _validation_checks(
        config_items, feature_toggles, secrets, operational_limits, evidence_references
    )
    rollback_defaults = _rollback_defaults(feature_toggles, integrations, operational_limits)
    owner_handoffs = _owner_handoffs(config_items, feature_toggles, secrets, operational_limits)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "domain": source.get("domain"),
            "category": source.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": title,
            "workflow_context": workflow,
            "stack": _stack_label(stack),
            "configuration_item_count": len(config_items),
            "feature_toggle_count": len(feature_toggles),
            "secret_count": len(secrets),
            "operational_limit_count": len(operational_limits),
            "validation_check_count": len(validation_checks),
            "rollback_default_count": len(rollback_defaults),
        },
        "configuration_items": config_items,
        "feature_toggles": feature_toggles,
        "secrets": secrets,
        "operational_limits": operational_limits,
        "validation_checks": validation_checks,
        "rollback_defaults": rollback_defaults,
        "owner_handoffs": owner_handoffs,
        "evidence_references": evidence_references,
    }


def render_runtime_configuration_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a runtime configuration plan as stable Markdown."""
    plan = plan if isinstance(plan, dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Runtime Configuration Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Kind: {_text(plan.get('kind'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Configuration items: {_text(summary.get('configuration_item_count'))}",
        f"- Feature toggles: {_text(summary.get('feature_toggle_count'))}",
        f"- Secrets: {_text(summary.get('secret_count'))}",
        "",
    ]

    _extend_section(lines, "Configuration Items", plan.get("configuration_items"), _render_config)
    _extend_section(lines, "Feature Toggles", plan.get("feature_toggles"), _render_toggle)
    _extend_section(lines, "Secrets", plan.get("secrets"), _render_secret)
    _extend_section(lines, "Operational Limits", plan.get("operational_limits"), _render_limit)
    _extend_section(lines, "Validation Checks", plan.get("validation_checks"), _render_check)
    _extend_section(lines, "Rollback Defaults", plan.get("rollback_defaults"), _render_rollback)
    _extend_section(lines, "Owner Handoffs", plan.get("owner_handoffs"), _render_handoff)

    lines.extend(["## Evidence References", ""])
    evidence = [_compact(item) for item in _list(plan.get("evidence_references")) if _compact(item)]
    if evidence:
        lines.extend(f"- {item}" for item in evidence)
    else:
        lines.append("None.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_runtime_configuration_plan_csv(plan: dict[str, Any]) -> str:
    """Render a runtime configuration plan as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(plan if isinstance(plan, dict) else {}):
        writer.writerow(row)
    return output.getvalue()


def _configuration_items(
    title: str, workflow: str, stack: Any, integrations: list[str]
) -> list[dict[str, Any]]:
    prefix = _env_prefix(title)
    items = [
        _config(
            "CFG1",
            "SERVICE_ENV",
            f"Identifies the active environment for logs, metrics, release gates, and {workflow}.",
            "platform_owner",
            "required",
            False,
            "staging",
            ["deployment.environment"],
        ),
        _config(
            "CFG2",
            "APP_BASE_URL",
            "Canonical service URL used by health checks, callbacks, and generated links.",
            "platform_owner",
            "required",
            False,
            "https://service.example.com",
            ["project.workflow_context", "solution.technical_approach"],
        ),
        _config(
            "CFG3",
            "LOG_LEVEL",
            "Structured logging verbosity for rollout, support, and incident response.",
            "service_owner",
            "required",
            False,
            "INFO",
            ["execution.validation_plan"],
        ),
        _config(
            "CFG4",
            f"{prefix}_CONFIG_VERSION",
            "Monotonic runtime configuration version used to coordinate validation and rollback.",
            "release_owner",
            "required",
            False,
            "1",
            ["execution.mvp_scope"],
        ),
    ]

    for env_name, purpose, owner, source_fields in _stack_configuration(stack):
        items.append(
            _config(
                f"CFG{len(items) + 1}",
                env_name,
                purpose,
                owner,
                "required",
                env_name.endswith("_URL") or env_name.endswith("_SECRET"),
                "managed secret reference" if env_name.endswith(("_URL", "_SECRET")) else "configured",
                source_fields,
            )
        )

    for integration in integrations:
        items.append(
            _config(
                f"CFG{len(items) + 1}",
                f"{_env_prefix(integration)}_BASE_URL",
                f"Base URL, workspace, or tenant identifier for {integration} runtime calls.",
                "integration_owner",
                "conditional",
                False,
                "vendor sandbox URL",
                ["solution.suggested_stack", "solution.composability_notes"],
            )
        )

    return _dedupe(items, prefix="CFG", key="name")


def _feature_toggles(title: str, integrations: list[str], execution: dict[str, Any]) -> list[dict[str, Any]]:
    prefix = _env_prefix(title)
    toggles = [
        _toggle(
            "FT1",
            f"{prefix}_FEATURE_ENABLED",
            "Primary exposure switch for the runtime path.",
            "launch_owner",
            "false",
            "Enable only after validation checks pass in the target environment.",
            ["execution.validation_plan"],
        )
    ]
    text = _haystack(execution)
    if integrations:
        toggles.append(
            _toggle(
                f"FT{len(toggles) + 1}",
                f"{prefix}_INTEGRATIONS_ENABLED",
                "Allows outbound vendor calls after sandbox and credential validation.",
                "integration_owner",
                "false",
                "Keep disabled during rollback or vendor incident response.",
                ["solution.suggested_stack", "solution.composability_notes"],
            )
        )
    if _has_any(text, ("write", "sync", "mutat", "update", "delete", "publish", "send")):
        toggles.append(
            _toggle(
                f"FT{len(toggles) + 1}",
                f"{prefix}_WRITE_ACTIONS_ENABLED",
                "Controls irreversible writes, notifications, syncs, and customer-visible side effects.",
                "service_owner",
                "false",
                "Enable after read-only workflow acceptance passes.",
                ["execution.mvp_scope", "execution.risks"],
            )
        )
    return toggles


def _secrets(stack: Any, integrations: list[str]) -> list[dict[str, Any]]:
    secrets: list[dict[str, Any]] = []
    stack_text = _haystack(stack)
    if _has_any(stack_text, ("postgres", "mysql", "database", "redis", "queue", "storage", "s3")):
        secrets.append(
            _secret(
                "SEC1",
                "DATA_STORE_CONNECTION",
                "Connection credentials for runtime persistence, cache, queue, or object storage.",
                "platform_owner",
                "managed secret store",
                ["solution.suggested_stack"],
            )
        )
    if _has_any(stack_text, ("auth", "oauth", "oidc", "saml", "sso", "jwt")):
        secrets.append(
            _secret(
                f"SEC{len(secrets) + 1}",
                "AUTH_CLIENT_SECRET",
                "Client secret, signing key, or token validation material for the identity boundary.",
                "security_owner",
                "managed secret store",
                ["solution.suggested_stack", "solution.technical_approach"],
            )
        )
    for integration in integrations:
        secrets.append(
            _secret(
                f"SEC{len(secrets) + 1}",
                f"{_env_prefix(integration)}_API_TOKEN",
                f"Scoped credential used to call {integration} from the runtime workflow.",
                "integration_owner",
                "managed secret store",
                ["solution.suggested_stack", "solution.composability_notes"],
            )
        )
    if not secrets:
        secrets.append(
            _secret(
                "SEC1",
                "RUNTIME_SECRET_PLACEHOLDER",
                "Placeholder for future credentials; remove if the implementation remains secret-free.",
                "platform_owner",
                "managed secret store",
                ["solution.technical_approach"],
            )
        )
    return _dedupe(secrets, prefix="SEC", key="name")


def _operational_limits(
    spec: dict[str, Any], execution: dict[str, Any], stack: Any
) -> list[dict[str, Any]]:
    text = _haystack({"spec": spec, "stack": stack})
    limits = [
        _limit(
            "LIM1",
            "REQUEST_TIMEOUT_SECONDS",
            "Maximum runtime request duration before failing closed with a retryable error.",
            "service_owner",
            "30",
            "Confirm slow dependency paths return a controlled timeout.",
            ["solution.technical_approach"],
        ),
        _limit(
            "LIM2",
            "MAX_RETRY_ATTEMPTS",
            "Caps transient dependency retries to avoid duplicate side effects and runaway costs.",
            "service_owner",
            "3",
            "Force dependency errors and verify bounded retries.",
            ["execution.risks", "solution.composability_notes"],
        ),
        _limit(
            "LIM3",
            "MAX_PAYLOAD_BYTES",
            "Rejects oversized request, webhook, import, or generated-output payloads.",
            "backend_owner",
            "1048576",
            "Submit boundary-size fixtures in smoke tests.",
            ["execution.validation_plan"],
        ),
    ]
    if _has_any(text, ("worker", "queue", "async", "background", "cron")):
        limits.append(
            _limit(
                f"LIM{len(limits) + 1}",
                "WORKER_CONCURRENCY",
                "Controls background job fan-out for queue, sync, and retry workloads.",
                "platform_owner",
                "2",
                "Run staging load checks before raising concurrency.",
                ["solution.suggested_stack", "execution.mvp_scope"],
            )
        )
    if _has_any(text, ("api", "webhook", "endpoint", "http")):
        limits.append(
            _limit(
                f"LIM{len(limits) + 1}",
                "RATE_LIMIT_PER_MINUTE",
                "Default per-user or per-integration request ceiling for exposed runtime endpoints.",
                "platform_owner",
                "100",
                "Verify throttled requests emit structured audit and support signals.",
                ["solution.technical_approach", "execution.risks"],
            )
        )
    return limits


def _validation_checks(
    config_items: list[dict[str, Any]],
    feature_toggles: list[dict[str, Any]],
    secrets: list[dict[str, Any]],
    operational_limits: list[dict[str, Any]],
    evidence_references: list[str],
) -> list[dict[str, Any]]:
    checks = [
        _check(
            "VAL1",
            "Required configuration present",
            "Fail startup when required non-secret settings are missing or empty.",
            "platform_owner",
            [item["name"] for item in config_items if item["required"] == "required"],
        ),
        _check(
            "VAL2",
            "Secret references resolve without disclosure",
            "Verify secret references exist and redact values from logs, errors, CSV, and Markdown.",
            "security_owner",
            [item["name"] for item in secrets],
        ),
        _check(
            "VAL3",
            "Feature toggles default closed",
            "Confirm every rollout and side-effect toggle starts false in new environments.",
            "launch_owner",
            [item["name"] for item in feature_toggles],
        ),
        _check(
            "VAL4",
            "Operational limits enforce safe bounds",
            "Exercise timeout, retry, payload, concurrency, and rate-limit boundaries in staging.",
            "qa_owner",
            [item["name"] for item in operational_limits],
        ),
    ]
    if evidence_references:
        checks.append(
            _check(
                "VAL5",
                "Evidence-linked acceptance path",
                "Attach validation evidence to the source insights or signals before launch approval.",
                "release_owner",
                evidence_references,
            )
        )
    return checks


def _rollback_defaults(
    feature_toggles: list[dict[str, Any]], integrations: list[str], limits: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    defaults = [
        _rollback(
            "RB1",
            "Disable primary rollout",
            "Set every runtime feature toggle to false before reverting code or data.",
            "launch_owner",
            [item["name"] for item in feature_toggles],
        ),
        _rollback(
            "RB2",
            "Restore diagnostic logging",
            "Return LOG_LEVEL to INFO after incident triage to avoid noisy or sensitive logs.",
            "service_owner",
            ["LOG_LEVEL=INFO"],
        ),
        _rollback(
            "RB3",
            "Constrain runtime limits",
            "Restore conservative request, retry, payload, and worker limits after rollback.",
            "platform_owner",
            [f"{item['name']}={item['default_value']}" for item in limits],
        ),
    ]
    if integrations:
        defaults.append(
            _rollback(
                f"RB{len(defaults) + 1}",
                "Disable vendor side effects",
                "Keep integration toggles off and point vendor settings at sandbox or no-op callbacks.",
                "integration_owner",
                [f"{_env_prefix(item)}_BASE_URL=sandbox" for item in integrations],
            )
        )
    return defaults


def _owner_handoffs(
    config_items: list[dict[str, Any]],
    feature_toggles: list[dict[str, Any]],
    secrets: list[dict[str, Any]],
    limits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups = [
        ("platform_owner", "Provision environment variables and safe operational limits.", config_items + limits),
        ("security_owner", "Approve secret handling and redaction behavior.", secrets),
        ("launch_owner", "Own rollout toggle state and rollback defaults.", feature_toggles),
    ]
    handoffs = []
    for index, (owner, action, items) in enumerate(groups, start=1):
        names = [_compact(item.get("name")) for item in items if isinstance(item, dict)]
        handoffs.append(
            {
                "id": f"OWN{index}",
                "owner": owner,
                "action": action,
                "items": [name for name in names if name],
            }
        )
    return handoffs


def _stack_configuration(stack: Any) -> list[tuple[str, str, str, list[str]]]:
    if not isinstance(stack, dict):
        return []
    items: list[tuple[str, str, str, list[str]]] = []
    for key, value in sorted(stack.items()):
        combined = f"{key} {_compact(value)}".lower()
        if any(term in combined for term in ("database", "postgres", "mysql", "sqlite")):
            items.append(("DATABASE_URL", "Connection reference for the primary relational data store.", "platform_owner", ["solution.suggested_stack.database"]))
        elif any(term in combined for term in ("queue", "broker", "pubsub", "sqs")):
            items.append(("QUEUE_URL", "Connection reference for asynchronous job dispatch.", "platform_owner", ["solution.suggested_stack.queue"]))
        elif "redis" in combined or "cache" in combined:
            items.append(("REDIS_URL", "Connection reference for cache or rate-limit state.", "platform_owner", ["solution.suggested_stack.cache"]))
        elif any(term in combined for term in ("storage", "s3", "blob")):
            items.append(("OBJECT_STORAGE_URL", "Connection reference for file or object storage.", "platform_owner", ["solution.suggested_stack.storage"]))
        elif any(term in combined for term in ("auth", "oauth", "oidc", "saml", "sso")):
            items.append(("AUTH_ISSUER_URL", "Issuer or tenant URL used to validate runtime identities.", "security_owner", ["solution.suggested_stack.auth"]))
        elif "observability" in combined or "datadog" in combined or "sentry" in combined:
            items.append(("OBSERVABILITY_ENV", "Environment tag used by traces, metrics, and error reporting.", "platform_owner", ["solution.suggested_stack.observability"]))
    return items


def _integrations(spec: dict[str, Any], stack: Any) -> list[str]:
    text = _haystack(spec)
    if isinstance(stack, dict):
        text = " ".join([text, *(_compact(value).lower() for _, value in sorted(stack.items()))])
    integrations = [
        label
        for label, terms in sorted(_INTEGRATION_TERMS.items())
        if any(_term_found(text, term) for term in terms)
    ]
    return list(dict.fromkeys(integrations))


def _evidence_references(spec: dict[str, Any]) -> list[str]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs: list[str] = []
    for field in ("insight_ids", "signal_ids", "source_idea_ids"):
        refs.extend(_compact(item) for item in _list(evidence.get(field)) if _compact(item))
    if _compact(evidence.get("rationale")):
        refs.append(_compact(evidence.get("rationale")))
    return list(dict.fromkeys(refs))


def _config(
    item_id: str,
    name: str,
    purpose: str,
    owner: str,
    required: str,
    secret: bool,
    default_value: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "purpose": _compact(purpose),
        "owner": owner,
        "required": required,
        "secret": secret,
        "default_value": _compact(default_value),
        "source_fields": source_fields,
    }


def _toggle(
    item_id: str,
    name: str,
    purpose: str,
    owner: str,
    rollback_default: str,
    notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "purpose": _compact(purpose),
        "owner": owner,
        "rollback_default": rollback_default,
        "notes": _compact(notes),
        "source_fields": source_fields,
    }


def _secret(
    item_id: str,
    name: str,
    purpose: str,
    owner: str,
    storage: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "purpose": _compact(purpose),
        "owner": owner,
        "storage": storage,
        "rotation": "rotate before launch and on suspected exposure",
        "source_fields": source_fields,
    }


def _limit(
    item_id: str,
    name: str,
    purpose: str,
    owner: str,
    default_value: str,
    validation: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "purpose": _compact(purpose),
        "owner": owner,
        "default_value": default_value,
        "validation": _compact(validation),
        "source_fields": source_fields,
    }


def _check(
    item_id: str, name: str, validation: str, owner: str, source_fields: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "validation": _compact(validation),
        "owner": owner,
        "source_fields": source_fields,
    }


def _rollback(
    item_id: str, name: str, rollback_default: str, owner: str, source_fields: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "rollback_default": _compact(rollback_default),
        "owner": owner,
        "source_fields": source_fields,
    }


def _dedupe(items: list[dict[str, Any]], *, prefix: str, key: str) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        deduped.setdefault(_compact(item.get(key)).lower(), item)
    return [
        {**item, "id": f"{prefix}{index}"}
        for index, item in enumerate(deduped.values(), start=1)
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _dict_items(plan.get("configuration_items")):
        rows.append(
            _csv_row(
                plan,
                section="configuration_items",
                type_="environment_variable",
                item=item,
                secret=item.get("secret"),
                default_value="[secret reference]" if item.get("secret") else item.get("default_value"),
            )
        )
    for item in _dict_items(plan.get("feature_toggles")):
        rows.append(
            _csv_row(
                plan,
                section="feature_toggles",
                type_="feature_toggle",
                item=item,
                rollback_default=item.get("rollback_default"),
                notes=item.get("notes"),
            )
        )
    for item in _dict_items(plan.get("secrets")):
        rows.append(
            _csv_row(
                plan,
                section="secrets",
                type_="secret_reference",
                item=item,
                secret=True,
                notes=f"Storage: {item.get('storage')}; Rotation: {item.get('rotation')}",
            )
        )
    for item in _dict_items(plan.get("operational_limits")):
        rows.append(
            _csv_row(
                plan,
                section="operational_limits",
                type_="limit",
                item=item,
                default_value=item.get("default_value"),
                validation=item.get("validation"),
            )
        )
    for item in _dict_items(plan.get("validation_checks")):
        rows.append(
            _csv_row(
                plan,
                section="validation_checks",
                type_="validation",
                item=item,
                validation=item.get("validation"),
            )
        )
    for item in _dict_items(plan.get("rollback_defaults")):
        rows.append(
            _csv_row(
                plan,
                section="rollback_defaults",
                type_="rollback",
                item=item,
                rollback_default=item.get("rollback_default"),
            )
        )
    for item in _dict_items(plan.get("owner_handoffs")):
        rows.append(
            _csv_row(
                plan,
                section="owner_handoffs",
                type_="handoff",
                item=item,
                name=item.get("owner"),
                notes=item.get("action"),
                source_fields=item.get("items"),
            )
        )
    for index, evidence in enumerate(_list(plan.get("evidence_references")), start=1):
        if _compact(evidence):
            rows.append(
                _csv_row(
                    plan,
                    section="evidence_references",
                    type_="evidence",
                    item={"id": f"EVD{index}", "name": evidence},
                    evidence_references=[evidence],
                )
            )
    return rows


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    type_: str,
    item: dict[str, Any],
    name: Any = None,
    secret: Any = None,
    default_value: Any = None,
    validation: Any = None,
    rollback_default: Any = None,
    source_fields: Any = None,
    evidence_references: Any = None,
    notes: Any = None,
) -> dict[str, str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "title": summary.get("title"),
        "item_id": item.get("id"),
        "name": name if name is not None else item.get("name"),
        "purpose": item.get("purpose"),
        "owner": item.get("owner"),
        "required": item.get("required"),
        "secret": secret,
        "default_value": default_value,
        "environment": item.get("environment"),
        "validation": validation,
        "rollback_default": rollback_default,
        "source_fields": source_fields if source_fields is not None else item.get("source_fields"),
        "evidence_references": evidence_references,
        "notes": notes,
    }
    return {column: _csv_text(values.get(column)) for column in RUNTIME_CONFIGURATION_PLAN_CSV_COLUMNS}


def _extend_section(lines: list[str], title: str, items: Any, renderer) -> None:
    lines.extend([f"## {title}", ""])
    dict_items = _dict_items(items)
    if not dict_items:
        lines.extend(["None.", ""])
        return
    for item in dict_items:
        lines.extend(renderer(item))
        lines.append("")


def _render_config(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Required: {_text(item.get('required'))}",
        f"- Secret: {_text(item.get('secret'))}",
        f"- Default: {_text('[secret reference]' if item.get('secret') else item.get('default_value'))}",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Source fields: {_join_code(item.get('source_fields'))}",
    ]


def _render_toggle(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Rollback default: {_text(item.get('rollback_default'))}",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Notes: {_text(item.get('notes'))}",
        f"- Source fields: {_join_code(item.get('source_fields'))}",
    ]


def _render_secret(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Storage: {_text(item.get('storage'))}",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Rotation: {_text(item.get('rotation'))}",
        f"- Source fields: {_join_code(item.get('source_fields'))}",
    ]


def _render_limit(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Default: {_text(item.get('default_value'))}",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Validation: {_text(item.get('validation'))}",
        f"- Source fields: {_join_code(item.get('source_fields'))}",
    ]


def _render_check(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Validation: {_text(item.get('validation'))}",
        f"- Source fields: {_join_code(item.get('source_fields'))}",
    ]


def _render_rollback(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Rollback default: {_text(item.get('rollback_default'))}",
        f"- Source fields: {_join_code(item.get('source_fields'))}",
    ]


def _render_handoff(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Items: {_join_code(item.get('items'))}",
    ]


def _workflow(project: dict[str, Any]) -> str:
    return _compact(project.get("workflow_context")) or _compact(project.get("summary")) or "primary workflow"


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
    return "unspecified"


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}: {_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    if isinstance(value, list | tuple | set):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    return _compact(value)


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _term_found(text: str, term: str) -> bool:
    if not term:
        return False
    if not term[0].isalnum() or not term[-1].isalnum():
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _haystack(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_haystack(value[key]) for key in sorted(value))
    if isinstance(value, list | tuple):
        return " ".join(_haystack(item) for item in value)
    return _compact(value).lower()


def _env_prefix(value: Any) -> str:
    compact = _compact(value).upper()
    compact = re.sub(r"[^A-Z0-9]+", "_", compact).strip("_")
    return compact or "SERVICE"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
