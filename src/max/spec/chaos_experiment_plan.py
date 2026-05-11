"""Generate deterministic chaos experiment plans for TactSpec previews."""

from __future__ import annotations

from typing import Any


CHAOS_EXPERIMENT_PLAN_SCHEMA_VERSION = "max-chaos-experiment-plan/v1"

_INTEGRATION_LABELS = {
    "github": "GitHub",
    "slack": "Slack",
    "stripe": "Stripe",
    "salesforce": "Salesforce",
    "openai": "OpenAI",
    "postgres": "Postgres",
    "mysql": "MySQL",
    "redis": "Redis",
    "s3": "S3",
    "bigquery": "BigQuery",
    "kafka": "Kafka",
}


def generate_chaos_experiment_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into a deterministic chaos experiment plan."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = _dict(spec.get("source"))
    project = _dict(spec.get("project"))
    solution = _dict(spec.get("solution"))
    execution = _dict(spec.get("execution"))
    evaluation = _dict(spec.get("evaluation"))

    workflow = _workflow(project, execution)
    integrations = _integrations(spec, solution)
    risks = _risks(spec, execution)
    acceptance_criteria = _acceptance_criteria(spec)
    weaknesses = _weaknesses(evaluation)
    stack = _stack_label(solution.get("suggested_stack"))
    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"

    context = {
        "title": title,
        "workflow_context": workflow,
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "stack": stack,
        "integrations": integrations,
        "risks": risks,
        "acceptance_criteria": acceptance_criteria,
        "weaknesses": weaknesses,
    }

    scenarios = _scenarios(context)
    guardrails = _guardrails(context)
    telemetry_checks = _telemetry_checks(context)
    abort_conditions = _abort_conditions(context)
    recovery_validation = _recovery_validation(context)

    return {
        "schema_version": CHAOS_EXPERIMENT_PLAN_SCHEMA_VERSION,
        "kind": "max.chaos_experiment_plan",
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
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "stack": stack,
            "integration_count": len(integrations),
            "scenario_count": len(scenarios),
            "risk_count": len(risks),
            "acceptance_criteria_count": len(acceptance_criteria),
            "evaluation_weakness_count": len(weaknesses),
        },
        "scenarios": scenarios,
        "guardrails": guardrails,
        "telemetry_checks": telemetry_checks,
        "abort_conditions": abort_conditions,
        "owner_roles": _owner_roles(context),
        "recovery_validation": recovery_validation,
    }


def render_chaos_experiment_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a generated chaos experiment plan as deterministic Markdown."""
    summary = _dict(plan.get("summary"))
    source = _dict(plan.get("source"))
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Chaos Experiment Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Scenarios: {_text(summary.get('scenario_count'))}",
        f"- Risks: {_text(summary.get('risk_count'))}",
        "",
    ]

    _extend_section(lines, "Scenarios", plan.get("scenarios") or [], _render_scenario)
    _extend_section(lines, "Guardrails", plan.get("guardrails") or [], _render_control)
    _extend_section(
        lines, "Telemetry Checks", plan.get("telemetry_checks") or [], _render_control
    )
    _extend_section(
        lines, "Abort Conditions", plan.get("abort_conditions") or [], _render_control
    )
    _extend_section(lines, "Owner Roles", plan.get("owner_roles") or [], _render_owner)
    _extend_section(
        lines,
        "Recovery Validation",
        plan.get("recovery_validation") or [],
        _render_control,
    )

    return "\n".join(lines).rstrip() + "\n"


def _scenarios(context: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = context["workflow_context"]
    integration = context["integrations"][0] if context["integrations"] else "primary dependency"
    risk = context["risks"][0] if context["risks"] else "unhandled dependency or latency failure"
    weakness = (
        context["weaknesses"][0]
        if context["weaknesses"]
        else "resilience assumptions need production-like validation"
    )
    criteria = (
        context["acceptance_criteria"][0]
        if context["acceptance_criteria"]
        else f"{workflow} completes with a clear user-visible outcome"
    )
    scenarios = [
        _scenario(
            "CHAOS1",
            "dependency_degradation",
            "integration",
            f"Degrade {integration} during {workflow}.",
            "Inject latency, throttling, or a 5xx response into the dependency boundary.",
            f"One pilot cohort, synthetic account, or canary path for {context['target_user']}.",
            ["solution.suggested_stack", "solution.composability_notes"],
            context,
        ),
        _scenario(
            "CHAOS2",
            "workflow_risk_probe",
            "workflow",
            f"Validate the workflow can tolerate: {risk}.",
            "Pause one non-critical worker, queue, webhook, or background step for a short window.",
            f"Only the {workflow} path; no shared storage mutation outside test fixtures.",
            ["execution.risks", "project.workflow_context"],
            context,
        ),
        _scenario(
            "CHAOS3",
            "acceptance_recovery_probe",
            "recovery",
            f"Confirm recovery still satisfies acceptance criterion: {_rstrip_period(criteria)}.",
            "Force a retryable failure, restore the dependency, and replay the affected request.",
            "Single reversible transaction or disposable fixture dataset.",
            ["acceptance_criteria", "execution.validation_plan"],
            context,
        ),
        _scenario(
            "CHAOS4",
            "evaluation_weakness_probe",
            "validation",
            f"Exercise evaluation weakness under stress: {weakness}.",
            "Run the validation flow while telemetry, retries, and operator handoff are observed.",
            "Pre-production or limited canary only until the weakness has explicit evidence.",
            ["evaluation.weaknesses"],
            context,
        ),
    ]
    return scenarios


def _scenario(
    scenario_id: str,
    name: str,
    category: str,
    hypothesis: str,
    injection: str,
    blast_radius: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "name": name,
        "category": category,
        "hypothesis": _compact(hypothesis),
        "injection": _compact(injection),
        "blast_radius": _compact(blast_radius),
        "guardrails": [item["id"] for item in _guardrails(context)],
        "abort_conditions": [item["id"] for item in _abort_conditions(context)],
        "telemetry_checks": [item["id"] for item in _telemetry_checks(context)],
        "owner_roles": ["experiment_owner", "service_owner", "on_call_owner"],
        "recovery_validation": [item["id"] for item in _recovery_validation(context)],
        "derived_from": derived_from,
    }


def _guardrails(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _control(
            "GR1",
            "limited_exposure",
            "Run only in pre-production, a canary cohort, or a synthetic tenant.",
            "experiment_owner",
            ["project.target_users", "project.workflow_context"],
        ),
        _control(
            "GR2",
            "fixture_isolation",
            "Use disposable fixtures or tagged test records and block destructive production writes.",
            "data_owner",
            ["execution.validation_plan", "acceptance_criteria"],
        ),
        _control(
            "GR3",
            "operator_presence",
            f"Keep service and on-call owners present for the {context['workflow_context']} window.",
            "on_call_owner",
            ["execution.risks"],
        ),
    ]


def _telemetry_checks(context: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = context["workflow_context"]
    return [
        _control(
            "TEL1",
            "workflow_success_rate",
            f"Track success, failure, retry, and timeout counts for {workflow}.",
            "service_owner",
            ["project.workflow_context", "observability_plan"],
        ),
        _control(
            "TEL2",
            "latency_and_saturation",
            "Watch p95 latency, queue depth, rate limit responses, and worker saturation.",
            "on_call_owner",
            ["solution.suggested_stack", "execution.risks"],
        ),
        _control(
            "TEL3",
            "user_visible_degradation",
            "Confirm errors are classified, user-visible messages are clear, and support signals emit.",
            "support_owner",
            ["acceptance_criteria", "project.value_proposition"],
        ),
    ]


def _abort_conditions(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _control(
            "AB1",
            "customer_or_data_impact",
            "Abort immediately if untagged customer data, billing, or irreversible side effects are touched.",
            "experiment_owner",
            ["guardrails.fixture_isolation"],
        ),
        _control(
            "AB2",
            "slo_breach",
            "Abort if error rate, latency, saturation, or queue depth exceeds the agreed test threshold.",
            "on_call_owner",
            ["telemetry_checks"],
        ),
        _control(
            "AB3",
            "acceptance_regression",
            (
                "Abort if a release-critical acceptance criterion fails after one retry or "
                f"the {context['workflow_context']} path cannot recover."
            ),
            "qa_owner",
            ["acceptance_criteria"],
        ),
    ]


def _recovery_validation(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _control(
            "RV1",
            "restore_dependency",
            "Remove the injection and confirm dependency health returns to baseline.",
            "service_owner",
            ["solution.suggested_stack"],
        ),
        _control(
            "RV2",
            "replay_workflow",
            f"Replay {context['workflow_context']} with the same fixture and compare the result.",
            "qa_owner",
            ["execution.validation_plan", "acceptance_criteria"],
        ),
        _control(
            "RV3",
            "evidence_capture",
            "Record timeline, telemetry screenshots, abort decisions, and follow-up owners.",
            "experiment_owner",
            ["evaluation.weaknesses", "execution.risks"],
        ),
    ]


def _owner_roles(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "OWN1",
            "role": "experiment_owner",
            "suggested_owner": context["buyer"],
            "responsibility": "Approves blast radius, starts and stops the experiment, and records decisions.",
        },
        {
            "id": "OWN2",
            "role": "service_owner",
            "suggested_owner": _service_owner(context["stack"]),
            "responsibility": "Owns dependency injection, runtime configuration, and recovery execution.",
        },
        {
            "id": "OWN3",
            "role": "on_call_owner",
            "suggested_owner": "on-call engineer",
            "responsibility": "Watches telemetry, executes abort criteria, and coordinates escalation.",
        },
        {
            "id": "OWN4",
            "role": "qa_owner",
            "suggested_owner": context["target_user"],
            "responsibility": "Owns fixtures, acceptance checks, and post-recovery validation evidence.",
        },
        {
            "id": "OWN5",
            "role": "support_owner",
            "suggested_owner": "support lead",
            "responsibility": "Verifies user-facing messaging and support signal capture.",
        },
        {
            "id": "OWN6",
            "role": "data_owner",
            "suggested_owner": "data or platform owner",
            "responsibility": "Confirms fixture isolation and data cleanup after the experiment.",
        },
    ]


def _control(
    control_id: str,
    name: str,
    description: str,
    owner: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": control_id,
        "name": name,
        "description": _compact(description),
        "owner": owner,
        "derived_from": derived_from,
    }


def _workflow(project: dict[str, Any], execution: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _first_string(execution.get("mvp_scope"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _integrations(spec: dict[str, Any], solution: dict[str, Any]) -> list[str]:
    haystack = _haystack([solution.get("suggested_stack"), solution, spec])
    found = [
        label
        for token, label in sorted(_INTEGRATION_LABELS.items(), key=lambda item: item[1])
        if token in haystack
    ]
    explicit = _list(solution.get("integrations")) + _list(solution.get("dependencies"))
    for item in explicit:
        label = _compact(item)
        if label:
            found.append(label)
    return _dedupe(found) or ["primary dependency"]


def _risks(spec: dict[str, Any], execution: dict[str, Any]) -> list[str]:
    risks = _list(execution.get("risks")) + _list(spec.get("risks"))
    risk_register = _dict(spec.get("risk_register"))
    risks.extend(_list(risk_register.get("risks")))
    return _dedupe(_compact_rich(item) for item in risks) or ["dependency degradation"]


def _acceptance_criteria(spec: dict[str, Any]) -> list[str]:
    values = []
    values.extend(_list(spec.get("acceptance_criteria")))
    values.extend(_list(_dict(spec.get("execution")).get("acceptance_criteria")))
    artifacts = _dict(spec.get("artifacts"))
    values.extend(_list(_dict(artifacts.get("acceptance_criteria")).get("criteria")))
    return _dedupe(_compact_rich(item) for item in values) or [
        "Primary workflow completes with no unresolved user-visible error."
    ]


def _weaknesses(evaluation: dict[str, Any]) -> list[str]:
    return _dedupe(_compact_rich(item) for item in _list(evaluation.get("weaknesses"))) or [
        "No evaluation weaknesses were provided; validate resilience assumptions explicitly."
    ]


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict):
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
        return "unspecified"
    if isinstance(stack, list | tuple | set):
        values = [_compact(item) for item in stack if _compact(item)]
        if values:
            return ", ".join(values)
        return "unspecified"
    return _compact(stack) or "unspecified"


def _service_owner(stack: str) -> str:
    if stack and stack != "unspecified":
        return f"{stack.split(',')[0]} owner"
    return "service owner"


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_scenario(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Hypothesis: {_text(item.get('hypothesis'))}",
        f"- Injection: {_text(item.get('injection'))}",
        f"- Blast radius: {_text(item.get('blast_radius'))}",
        f"- Guardrails: {_join_code(item.get('guardrails'))}",
        f"- Abort conditions: {_join_code(item.get('abort_conditions'))}",
        f"- Telemetry checks: {_join_code(item.get('telemetry_checks'))}",
        f"- Owner roles: {_join_code(item.get('owner_roles'))}",
        f"- Recovery validation: {_join_code(item.get('recovery_validation'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_control(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
    ]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first_string(value: Any) -> str:
    for item in _list(value):
        text = _compact_rich(item)
        if text:
            return text
    return ""


def _compact_rich(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("description", "criterion", "name", "title", "risk", "summary"):
            text = _compact(value.get(key))
            if text:
                return text
        return _compact(value)
    return _compact(value)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _rstrip_period(value: Any) -> str:
    return _compact(value).rstrip(".")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe(values: Any) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            deduped.append(text)
    return deduped


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _haystack(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(_compact(key))
            parts.append(_haystack(item))
        return " ".join(parts).casefold()
    if isinstance(value, list | tuple | set):
        return " ".join(_haystack(item) for item in value).casefold()
    return _compact(value).casefold()
