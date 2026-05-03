"""Generate deterministic deployment topology plans for TactSpec previews."""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import Any


DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION = "max-deployment-topology/v1"
DEPLOYMENT_TOPOLOGY_CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "title",
    "item_id",
    "name",
    "category",
    "technology",
    "purpose",
    "network_boundary",
    "required",
    "secret",
    "example",
    "traffic",
    "controls",
    "owner",
    "action",
    "dependencies",
    "environment",
    "isolation",
    "note",
    "description",
    "derived_from",
)

_EXTERNAL_INTEGRATION_TERMS = {
    "Azure DevOps": ("azure devops",),
    "Datadog": ("datadog",),
    "GitHub": ("github",),
    "Jira": ("jira", "atlassian"),
    "Linear": ("linear",),
    "OpenAI": ("openai", "llm", "embedding", "model provider"),
    "Salesforce": ("salesforce",),
    "Sentry": ("sentry",),
    "Slack": ("slack",),
    "Stripe": ("stripe",),
    "Teams": ("microsoft teams",),
}

_BACKING_SERVICE_TERMS = {
    "Postgres": ("postgres", "postgresql"),
    "Redis": ("redis",),
    "Queue": ("queue", "sqs", "pubsub", "pub/sub", "celery", "worker queue"),
    "Object storage": ("object storage", "s3", "blob storage", "gcs"),
    "Search index": ("search index", "elasticsearch", "opensearch", "meilisearch"),
    "Vector store": ("vector store", "pgvector", "pinecone", "weaviate", "qdrant"),
}


def generate_deployment_topology(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic deployment topology guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    stack = solution.get("suggested_stack")

    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    workflow = _workflow(project)
    acceptance_criteria = _acceptance_criteria(spec)
    risks = _risks(spec, execution, evaluation)
    integrations = _external_integrations(spec, stack)
    backing_services = _backing_services(spec, stack)
    runtime_components = _runtime_components(title, workflow, solution, execution, stack)
    secrets = _configuration_items(title, stack, integrations, backing_services)

    return {
        "schema_version": DEPLOYMENT_TOPOLOGY_SCHEMA_VERSION,
        "kind": "max.deployment_topology",
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
            "target_user": _compact(project.get("specific_user") or project.get("target_users"))
            or "primary user",
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "stack": _stack_label(stack),
            "runtime_component_count": len(runtime_components),
            "backing_service_count": len(backing_services),
            "external_service_count": len(integrations),
            "secret_count": sum(1 for item in secrets if item["secret"]),
        },
        "topology": {
            "runtime_components": runtime_components,
            "backing_services": backing_services,
            "external_services": integrations,
            "configuration": secrets,
            "network_boundaries": _network_boundaries(
                runtime_components, backing_services, integrations, stack
            ),
            "deployment_sequence": _deployment_sequence(
                runtime_components, backing_services, integrations, acceptance_criteria
            ),
        },
        "environments": _environments(integrations, backing_services),
        "operational_notes": _operational_notes(workflow, risks, acceptance_criteria, integrations),
        "assumptions": _assumptions(project, solution, integrations, backing_services),
    }


def render_deployment_topology_markdown(topology: dict[str, Any]) -> str:
    """Render a generated deployment topology as a stable markdown handoff document."""
    summary = topology.get("summary", {})
    source = topology.get("source", {})
    body = topology.get("topology", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Deployment Topology",
        "",
        f"- Schema version: {_text(topology.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        "",
    ]

    _extend_section(
        lines, "Topology - Runtime Components", body.get("runtime_components") or [], _render_node
    )
    _extend_section(
        lines, "Topology - Backing Services", body.get("backing_services") or [], _render_node
    )
    _extend_section(
        lines, "Topology - External Services", body.get("external_services") or [], _render_node
    )
    _extend_section(
        lines, "Configuration and Secrets", body.get("configuration") or [], _render_config
    )
    _extend_section(
        lines, "Network Boundaries", body.get("network_boundaries") or [], _render_boundary
    )
    _extend_section(
        lines, "Deployment Sequence", body.get("deployment_sequence") or [], _render_step
    )
    _extend_section(lines, "Environments", topology.get("environments") or [], _render_environment)
    _extend_section(
        lines, "Operational Notes", topology.get("operational_notes") or [], _render_note
    )

    lines.extend(["## Assumptions", ""])
    assumptions = topology.get("assumptions") or []
    if assumptions:
        lines.extend(f"- {_text(item)}" for item in assumptions)
    else:
        lines.append("None.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_deployment_topology_csv(topology: dict[str, Any]) -> str:
    """Render a generated deployment topology as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output, fieldnames=DEPLOYMENT_TOPOLOGY_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in _csv_rows(topology):
        writer.writerow(row)
    return output.getvalue()


def render_deployment_topology_json(topology: dict[str, Any]) -> str:
    """Render a generated deployment topology as deterministic pretty-printed JSON."""
    return json.dumps(topology, indent=2, sort_keys=True) + "\n"


def _runtime_components(
    title: str,
    workflow: str,
    solution: dict[str, Any],
    execution: dict[str, Any],
    stack: Any,
) -> list[dict[str, Any]]:
    text = _haystack({"solution": solution, "execution": execution})
    components = [
        _node(
            "CMP1",
            "application-runtime",
            title,
            f"Primary runtime for the {workflow} path.",
            _runtime_technology(stack),
            "private application subnet or managed app runtime",
            ["project.workflow_context", "solution.suggested_stack"],
        )
    ]
    if _has_any(text, ("api", "webhook", "http", "fastapi", "django", "flask", "express")):
        components.append(
            _node(
                f"CMP{len(components) + 1}",
                "api",
                "API ingress",
                "Handles user, webhook, or integration requests before dispatching workflow work.",
                _stack_value(stack, ("backend", "framework", "api")) or "web/API service",
                "public ingress behind TLS and authentication controls",
                ["solution.technical_approach", "solution.suggested_stack"],
            )
        )
    if _has_any(text, ("frontend", "ui", "console", "dashboard", "react", "next.js", "vue")):
        components.append(
            _node(
                f"CMP{len(components) + 1}",
                "frontend",
                "User interface",
                "Provides the target-user surface for configuring, reviewing, or completing the workflow.",
                _stack_value(stack, ("frontend", "ui")) or "web frontend",
                "public web edge with static assets or SSR runtime",
                ["project.target_users", "solution.suggested_stack"],
            )
        )
    if _has_any(text, ("worker", "background", "queue", "async", "scheduled", "cron", "celery")):
        components.append(
            _node(
                f"CMP{len(components) + 1}",
                "worker",
                "Background worker",
                "Runs asynchronous jobs, retries, scheduled checks, or integration fan-out.",
                _stack_value(stack, ("worker", "queue")) or "background worker",
                "private worker subnet with outbound dependency access",
                ["execution.mvp_scope", "solution.technical_approach"],
            )
        )
    if _has_any(text, ("cli", "command line", "runner")):
        components.append(
            _node(
                f"CMP{len(components) + 1}",
                "cli",
                "Command runner",
                "Runs operator-triggered or CI-triggered deployment and validation commands.",
                _stack_value(stack, ("cli", "language")) or "CLI runtime",
                "trusted operator or CI execution environment",
                ["execution.validation_plan", "solution.technical_approach"],
            )
        )
    return _dedupe_nodes(components)


def _backing_services(spec: dict[str, Any], stack: Any) -> list[dict[str, Any]]:
    text = _haystack(spec)
    services: list[dict[str, Any]] = []
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            label = _service_label(str(key), value)
            if label:
                services.append(
                    _node(
                        f"DAT{len(services) + 1}",
                        "backing-service",
                        label,
                        f"Managed {label} dependency required by the application runtime.",
                        _compact(value) or label,
                        "private network or vendor-managed encrypted service",
                        ["solution.suggested_stack"],
                    )
                )
    for label, terms in sorted(_BACKING_SERVICE_TERMS.items()):
        if any(term in text for term in terms):
            services.append(
                _node(
                    f"DAT{len(services) + 1}",
                    "backing-service",
                    label,
                    f"Conservative backing service assumption because the spec references {label.lower()} behavior.",
                    label,
                    "private network or vendor-managed encrypted service",
                    ["solution.technical_approach", "execution.risks"],
                )
            )
    return _dedupe_nodes(services, prefix="DAT")


def _external_integrations(spec: dict[str, Any], stack: Any) -> list[dict[str, Any]]:
    text = _haystack(spec)
    if isinstance(stack, dict):
        text = " ".join([text, *(_compact(value).lower() for _, value in sorted(stack.items()))])
    integrations = [
        _node(
            f"EXT{index}",
            "external-service",
            label,
            "External integration used by the primary workflow or operational handoff.",
            label,
            "controlled outbound egress over TLS",
            ["solution.suggested_stack", "solution.technical_approach", "execution.mvp_scope"],
        )
        for index, (label, terms) in enumerate(sorted(_EXTERNAL_INTEGRATION_TERMS.items()), start=1)
        if any(_term_found(text, term) for term in terms)
    ]
    return _dedupe_nodes(integrations, prefix="EXT")


def _configuration_items(
    title: str,
    stack: Any,
    integrations: list[dict[str, Any]],
    backing_services: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prefix = _env_prefix(title)
    items = [
        _config(
            "CFG1",
            "SERVICE_ENV",
            "Environment name used by logs, metrics, and release gates.",
            False,
            "production",
            ["environments"],
        ),
        _config(
            "CFG2",
            "APP_BASE_URL",
            "Canonical base URL or service endpoint for health checks and callbacks.",
            False,
            "https://service.example.com",
            ["network_boundaries"],
        ),
        _config(
            "CFG3",
            f"{prefix}_FEATURE_ENABLED",
            "Rollout flag that can disable new exposure without redeploying.",
            False,
            "false until launch approval",
            ["deployment_sequence"],
        ),
        _config(
            "CFG4",
            "LOG_LEVEL",
            "Structured log verbosity for rollout and incident response.",
            False,
            "INFO",
            ["operational_notes"],
        ),
    ]
    for service in backing_services:
        name = _compact(service.get("name"))
        env_name = _backing_service_env_name(name)
        items.append(
            _config(
                f"CFG{len(items) + 1}",
                env_name,
                f"Connection setting for {name}.",
                True,
                "managed secret",
                ["topology.backing_services"],
            )
        )
    for integration in integrations:
        name = _compact(integration.get("name"))
        items.append(
            _config(
                f"CFG{len(items) + 1}",
                f"{_env_prefix(name)}_API_TOKEN",
                f"Credential, token, or webhook secret for {name}.",
                True,
                "managed secret",
                ["topology.external_services"],
            )
        )
    if isinstance(stack, dict):
        auth = _stack_value(stack, ("auth", "identity", "sso"))
        if auth:
            items.append(
                _config(
                    f"CFG{len(items) + 1}",
                    "AUTH_CLIENT_SECRET",
                    f"Client secret or signing key for {auth}.",
                    True,
                    "managed secret",
                    ["solution.suggested_stack"],
                )
            )
    return _dedupe_config(items)


def _network_boundaries(
    components: list[dict[str, Any]],
    backing_services: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
    stack: Any,
) -> list[dict[str, Any]]:
    boundaries = [
        _boundary(
            "NET1",
            "public-ingress",
            "Users, webhooks, or CI systems enter through a single TLS-terminated ingress.",
            "Public internet to application runtime",
            ["APP_BASE_URL"],
        ),
        _boundary(
            "NET2",
            "runtime-private-zone",
            "Application components communicate on private service networking where the platform supports it.",
            "Application runtime to internal components",
            [item["id"] for item in components],
        ),
    ]
    if backing_services:
        boundaries.append(
            _boundary(
                "NET3",
                "data-plane",
                "Backing services stay private, encrypted at rest, and reachable only from approved runtimes.",
                "Application runtime to backing services",
                [item["id"] for item in backing_services],
            )
        )
    if integrations:
        boundaries.append(
            _boundary(
                f"NET{len(boundaries) + 1}",
                "vendor-egress",
                "Outbound integration traffic uses scoped credentials, retries, and audit logging.",
                "Application runtime to external services",
                [item["id"] for item in integrations],
            )
        )
    if not _stack_value(stack, ("auth", "identity", "sso")):
        boundaries.append(
            _boundary(
                f"NET{len(boundaries) + 1}",
                "authentication-boundary",
                "Authentication is unspecified; require an explicit auth decision before exposing production ingress.",
                "Public users to protected workflow",
                ["SERVICE_ENV", "APP_BASE_URL"],
            )
        )
    return boundaries


def _deployment_sequence(
    components: list[dict[str, Any]],
    backing_services: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
    acceptance_criteria: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    steps = [
        _step(
            "DEP1",
            "Prepare environment",
            "Create staging and production environment records, rollout flag, observability routing, and managed secrets.",
            "release_owner",
            ["SERVICE_ENV", "LOG_LEVEL"],
        ),
    ]
    if backing_services:
        steps.append(
            _step(
                f"DEP{len(steps) + 1}",
                "Provision backing services",
                "Provision data stores and apply migrations or baseline schemas before application rollout.",
                "platform_owner",
                [item["id"] for item in backing_services],
            )
        )
    steps.append(
        _step(
            f"DEP{len(steps) + 1}",
            "Deploy runtime components",
            "Deploy application runtime components in dependency order, then verify liveness before enabling traffic.",
            "service_owner",
            [item["id"] for item in components],
        )
    )
    if integrations:
        steps.append(
            _step(
                f"DEP{len(steps) + 1}",
                "Configure external integrations",
                "Install app credentials, webhook callbacks, allowlists, and sandbox-to-production vendor settings.",
                "integration_owner",
                [item["id"] for item in integrations],
            )
        )
    steps.append(
        _step(
            f"DEP{len(steps) + 1}",
            "Run validation gates",
            "Run smoke tests and release-critical acceptance criteria against the candidate environment.",
            "qa_owner",
            ["acceptance_criteria"] if acceptance_criteria else ["primary_workflow_smoke_test"],
        )
    )
    steps.append(
        _step(
            f"DEP{len(steps) + 1}",
            "Enable controlled rollout",
            "Enable the feature flag for the first cohort, monitor errors, and keep rollback ownership staffed.",
            "launch_owner",
            ["rollout_flag", "operational_notes"],
        )
    )
    return steps


def _environments(
    integrations: list[dict[str, Any]], backing_services: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        _environment(
            "ENV1",
            "local",
            "Developer validation with fake or sandbox credentials only.",
            "No production data; use fixture-backed dependencies.",
        ),
        _environment(
            "ENV2",
            "staging",
            "Production-like topology for acceptance criteria, migrations, and integration callbacks.",
            "Use isolated data stores and vendor sandboxes where available.",
        ),
        _environment(
            "ENV3",
            "production",
            "Customer-facing deployment with managed secrets, monitored dependencies, and rollback controls.",
            _production_isolation_note(integrations, backing_services),
        ),
    ]


def _operational_notes(
    workflow: str,
    risks: list[str],
    acceptance_criteria: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    notes = [
        _note(
            "OPS1",
            "health",
            f"Define a liveness probe and a fixture-backed readiness check for the {workflow} path.",
            ["project.workflow_context"],
        ),
        _note(
            "OPS2",
            "rollback",
            "Keep rollout flag, last known-good artifact, and deployment command available before production exposure.",
            ["deployment_sequence"],
        ),
        _note(
            "OPS3",
            "observability",
            "Emit structured logs, success/failure counters, latency, and dependency error tags from every runtime component.",
            ["observability"],
        ),
    ]
    if integrations:
        notes.append(
            _note(
                f"OPS{len(notes) + 1}",
                "dependency",
                "Separate vendor dependency failures from application failures in dashboards and alerts.",
                [item["id"] for item in integrations],
            )
        )
    if acceptance_criteria:
        notes.append(
            _note(
                f"OPS{len(notes) + 1}",
                "validation",
                "Map release-critical acceptance criteria to smoke checks before enabling rollout.",
                ["acceptance_criteria"],
            )
        )
    if risks:
        notes.append(
            _note(
                f"OPS{len(notes) + 1}",
                "risk",
                f"Assign owners for known risks before launch: {risks[0]}",
                ["execution.risks", "evaluation.weaknesses"],
            )
        )
    return notes


def _assumptions(
    project: dict[str, Any],
    solution: dict[str, Any],
    integrations: list[dict[str, Any]],
    backing_services: list[dict[str, Any]],
) -> list[str]:
    assumptions = []
    if not _compact(project.get("workflow_context")):
        assumptions.append(
            "Workflow context is missing; topology treats the primary workflow as the deployable value path."
        )
    if (
        not _stack_label(solution.get("suggested_stack"))
        or _stack_label(solution.get("suggested_stack")) == "unspecified"
    ):
        assumptions.append(
            "Suggested stack is missing; topology keeps runtime and hosting guidance platform-neutral."
        )
    if not backing_services:
        assumptions.append(
            "No backing data store is named; assume stateless runtime until persistence is explicitly added."
        )
    if not integrations:
        assumptions.append(
            "No external integration is detected; keep egress closed except for deployment and observability needs."
        )
    if not _stack_value(solution.get("suggested_stack"), ("auth", "identity", "sso")):
        assumptions.append(
            "Authentication is not explicit; require an auth boundary decision before production ingress."
        )
    return assumptions


def _node(
    node_id: str,
    category: str,
    name: str,
    purpose: str,
    technology: str,
    boundary: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "category": category,
        "name": _compact(name),
        "purpose": _compact(purpose),
        "technology": _compact(technology) or "unspecified",
        "network_boundary": _compact(boundary),
        "derived_from": [item for item in derived_from if _compact(item)],
    }


def _config(
    config_id: str,
    name: str,
    description: str,
    secret: bool,
    example: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": config_id,
        "name": name,
        "description": _compact(description),
        "required": "required",
        "secret": secret,
        "example": _compact(example),
        "derived_from": [item for item in derived_from if _compact(item)],
    }


def _boundary(
    boundary_id: str,
    name: str,
    description: str,
    traffic: str,
    controls: list[str],
) -> dict[str, Any]:
    return {
        "id": boundary_id,
        "name": name,
        "description": _compact(description),
        "traffic": _compact(traffic),
        "controls": [item for item in controls if _compact(item)],
    }


def _step(
    step_id: str, name: str, action: str, owner: str, dependencies: list[str]
) -> dict[str, Any]:
    return {
        "id": step_id,
        "name": name,
        "action": _compact(action),
        "owner": owner,
        "dependencies": [item for item in dependencies if _compact(item)],
    }


def _environment(env_id: str, name: str, purpose: str, isolation: str) -> dict[str, Any]:
    return {
        "id": env_id,
        "name": name,
        "purpose": _compact(purpose),
        "isolation": _compact(isolation),
    }


def _note(note_id: str, category: str, note: str, derived_from: list[str]) -> dict[str, Any]:
    return {
        "id": note_id,
        "category": category,
        "note": _compact(note),
        "derived_from": [item for item in derived_from if _compact(item)],
    }


def _acceptance_criteria(spec: dict[str, Any]) -> list[dict[str, Any]]:
    criteria = (
        spec.get("acceptance_criteria") if isinstance(spec.get("acceptance_criteria"), dict) else {}
    )
    items: list[dict[str, Any]] = []
    for key in ("functional_criteria", "non_functional_criteria"):
        for item in _list(criteria.get(key)):
            if isinstance(item, dict):
                items.append(item)
    return items


def _risks(
    spec: dict[str, Any], execution: dict[str, Any], evaluation: dict[str, Any]
) -> list[str]:
    risks = [_compact(item) for item in _list(execution.get("risks")) if _compact(item)]
    risk_register = spec.get("risk_register") if isinstance(spec.get("risk_register"), dict) else {}
    for risk in _list(risk_register.get("risks")):
        if isinstance(risk, dict):
            text = _compact(risk.get("description") or risk.get("title"))
            if text:
                risks.append(text)
    risks.extend(_compact(item) for item in _list(evaluation.get("weaknesses")) if _compact(item))
    return list(dict.fromkeys(risks))


def _service_label(key: str, value: Any) -> str:
    combined = f"{key} {_compact(value)}".lower()
    if any(term in combined for term in ("database", "datastore", "postgres", "mysql", "sqlite")):
        return _compact(value) or "Database"
    if "redis" in combined or "cache" in combined:
        return _compact(value) or "Cache"
    if any(term in combined for term in ("queue", "broker", "pubsub", "pub/sub", "sqs")):
        return _compact(value) or "Queue"
    if any(term in combined for term in ("storage", "s3", "blob")):
        return _compact(value) or "Object storage"
    if "search" in combined:
        return _compact(value) or "Search index"
    if "vector" in combined or "embedding" in combined:
        return _compact(value) or "Vector store"
    return ""


def _runtime_technology(stack: Any) -> str:
    if isinstance(stack, dict):
        values = [
            _compact(stack.get(key))
            for key in ("language", "framework", "backend", "runtime", "hosting")
            if _compact(stack.get(key))
        ]
        if values:
            return " / ".join(dict.fromkeys(values))
    return "application runtime"


def _stack_value(stack: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(stack, dict):
        return ""
    for key in keys:
        if _compact(stack.get(key)):
            return _compact(stack[key])
    return ""


def _backing_service_env_name(name: str) -> str:
    lower = name.lower()
    if "postgres" in lower or "database" in lower or "mysql" in lower:
        return "DATABASE_URL"
    if "redis" in lower or "cache" in lower:
        return "REDIS_URL"
    if "queue" in lower:
        return "QUEUE_URL"
    if "storage" in lower or "s3" in lower or "blob" in lower:
        return "OBJECT_STORAGE_URL"
    if "search" in lower:
        return "SEARCH_ENDPOINT"
    if "vector" in lower or "pinecone" in lower or "qdrant" in lower:
        return "VECTOR_STORE_URL"
    return f"{_env_prefix(name)}_URL"


def _production_isolation_note(
    integrations: list[dict[str, Any]], backing_services: list[dict[str, Any]]
) -> str:
    parts = ["Separate production secrets from all lower environments"]
    if backing_services:
        parts.append("use isolated production data stores")
    if integrations:
        parts.append("use production vendor apps with scoped credentials")
    return "; ".join(parts) + "."


def _dedupe_nodes(nodes: list[dict[str, Any]], *, prefix: str = "CMP") -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for node in nodes:
        key = (_compact(node.get("category")).lower(), _compact(node.get("name")).lower())
        deduped.setdefault(key, node)
    return [
        {**node, "id": f"{prefix}{index}"} for index, node in enumerate(deduped.values(), start=1)
    ]


def _dedupe_config(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        deduped.setdefault(item["name"], item)
    return [{**item, "id": f"CFG{index}"} for index, item in enumerate(deduped.values(), start=1)]


def _workflow(project: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
    return "unspecified"


def _external_integration_labels(nodes: list[dict[str, Any]]) -> list[str]:
    return [_compact(item.get("name")) for item in nodes if _compact(item.get("name"))]


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


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_node(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Technology: {_text(item.get('technology'))}",
        f"- Network boundary: {_text(item.get('network_boundary'))}",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_config(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Required: {_text(item.get('required'))}",
        f"- Secret: {_text(item.get('secret'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Example: {_text(item.get('example'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_boundary(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Traffic: {_text(item.get('traffic'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Controls: {_join_code(item.get('controls'))}",
    ]


def _render_step(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Dependencies: {_join_code(item.get('dependencies'))}",
    ]


def _render_environment(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Isolation: {_text(item.get('isolation'))}",
    ]


def _render_note(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        f"- Note: {_text(item.get('note'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _csv_rows(topology: dict[str, Any]) -> list[dict[str, str]]:
    body = topology.get("topology") if isinstance(topology.get("topology"), dict) else {}
    rows: list[dict[str, str]] = []

    for item in _dict_items(body.get("runtime_components")):
        rows.append(
            _csv_row(
                topology,
                section="runtime_components",
                type_="component",
                item_id=item.get("id"),
                name=item.get("name"),
                category=item.get("category"),
                technology=item.get("technology"),
                purpose=item.get("purpose"),
                network_boundary=item.get("network_boundary"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(body.get("backing_services")):
        rows.append(
            _csv_row(
                topology,
                section="backing_services",
                type_="service",
                item_id=item.get("id"),
                name=item.get("name"),
                category=item.get("category"),
                technology=item.get("technology"),
                purpose=item.get("purpose"),
                network_boundary=item.get("network_boundary"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(body.get("external_services")):
        rows.append(
            _csv_row(
                topology,
                section="external_services",
                type_="integration",
                item_id=item.get("id"),
                name=item.get("name"),
                category=item.get("category"),
                technology=item.get("technology"),
                purpose=item.get("purpose"),
                network_boundary=item.get("network_boundary"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(body.get("configuration")):
        rows.append(
            _csv_row(
                topology,
                section="configuration",
                type_="setting",
                item_id=item.get("id"),
                name=item.get("name"),
                required=item.get("required"),
                secret=item.get("secret"),
                example="[redacted]" if item.get("secret") is True else item.get("example"),
                description=item.get("description"),
                derived_from=item.get("derived_from"),
            )
        )

    for item in _dict_items(body.get("network_boundaries")):
        rows.append(
            _csv_row(
                topology,
                section="network_boundaries",
                type_="boundary",
                item_id=item.get("id"),
                name=item.get("name"),
                traffic=item.get("traffic"),
                controls=item.get("controls"),
                description=item.get("description"),
            )
        )

    for item in _dict_items(body.get("deployment_sequence")):
        rows.append(
            _csv_row(
                topology,
                section="deployment_sequence",
                type_="step",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                action=item.get("action"),
                dependencies=item.get("dependencies"),
            )
        )

    for item in _dict_items(topology.get("environments")):
        rows.append(
            _csv_row(
                topology,
                section="environments",
                type_="environment",
                item_id=item.get("id"),
                name=item.get("name"),
                environment=item.get("name"),
                purpose=item.get("purpose"),
                isolation=item.get("isolation"),
            )
        )

    for item in _dict_items(topology.get("operational_notes")):
        rows.append(
            _csv_row(
                topology,
                section="operational_notes",
                type_="note",
                item_id=item.get("id"),
                name=item.get("category"),
                category=item.get("category"),
                note=item.get("note"),
                derived_from=item.get("derived_from"),
            )
        )

    assumptions = _list(topology.get("assumptions"))
    assumption_row_count = 0
    for index, assumption in enumerate(assumptions, start=1):
        if not _csv_text(assumption):
            continue
        assumption_row_count += 1
        rows.append(
            _csv_row(
                topology,
                section="assumptions",
                type_="assumption",
                item_id=f"ASM{index}",
                description=assumption,
            )
        )
    if assumption_row_count == 0:
        rows.append(
            _csv_row(
                topology,
                section="assumptions",
                type_="assumption",
                item_id="ASM0",
                description="none",
            )
        )

    return rows


def _csv_row(
    topology: dict[str, Any],
    *,
    section: str,
    type_: str,
    item_id: Any = None,
    name: Any = None,
    category: Any = None,
    technology: Any = None,
    purpose: Any = None,
    network_boundary: Any = None,
    required: Any = None,
    secret: Any = None,
    example: Any = None,
    traffic: Any = None,
    controls: Any = None,
    owner: Any = None,
    action: Any = None,
    dependencies: Any = None,
    environment: Any = None,
    isolation: Any = None,
    note: Any = None,
    description: Any = None,
    derived_from: Any = None,
) -> dict[str, str]:
    source = topology.get("source") if isinstance(topology.get("source"), dict) else {}
    summary = topology.get("summary") if isinstance(topology.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "title": summary.get("title"),
        "item_id": item_id,
        "name": name,
        "category": category,
        "technology": technology,
        "purpose": purpose,
        "network_boundary": network_boundary,
        "required": required,
        "secret": secret,
        "example": example,
        "traffic": traffic,
        "controls": controls,
        "owner": owner,
        "action": action,
        "dependencies": dependencies,
        "environment": environment,
        "isolation": isolation,
        "note": note,
        "description": description,
        "derived_from": derived_from,
    }
    return {column: _csv_text(values.get(column)) for column in DEPLOYMENT_TOPOLOGY_CSV_COLUMNS}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


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


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
