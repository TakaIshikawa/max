"""Generate deterministic smoke test plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


SMOKE_TEST_PLAN_SCHEMA_VERSION = "max-smoke-test-plan/v1"
SMOKE_TEST_PLAN_CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "source_status",
    "tact_spec_schema_version",
    "title",
    "workflow_context",
    "target_user",
    "buyer",
    "stack",
    "validation_plan",
    "recommendation",
    "overall_score",
    "item_id",
    "name",
    "category",
    "status",
    "owner",
    "suggested_owner",
    "responsibility",
    "description",
    "expected_result",
    "derived_from",
    "evidence_reference_ids",
    "evidence_type",
    "evidence_summary",
)


def generate_smoke_test_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into immediate post-deploy verification checks."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    workflow = _workflow(project, execution)
    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    target_user = (
        _compact(project.get("specific_user") or project.get("target_users")) or "primary user"
    )
    buyer = _compact(project.get("buyer")) or "launch sponsor"
    stack = _stack_label(solution.get("suggested_stack"))
    validation_plan = (
        _compact(execution.get("validation_plan"))
        or f"Run the primary {workflow} path against the deployed build."
    )
    evidence_references = _evidence_references(spec)
    evidence_ids = [reference["id"] for reference in evidence_references]

    summary = {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "stack": stack,
        "validation_plan": validation_plan,
        "recommendation": evaluation.get("recommendation") if evaluation else None,
        "overall_score": evaluation.get("overall_score") if evaluation else None,
    }

    return {
        "schema_version": SMOKE_TEST_PLAN_SCHEMA_VERSION,
        "kind": "max.smoke_test_plan",
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
        "summary": summary,
        "user_journey_checks": _user_journey_checks(summary, execution, evidence_ids),
        "deployment_verification_checks": _deployment_verification_checks(
            summary, solution, evidence_ids
        ),
        "integration_checks": _integration_checks(summary, solution, execution, evidence_ids),
        "data_integrity_checks": _data_integrity_checks(summary, evidence_ids),
        "observability_checks": _observability_checks(summary, evidence_ids),
        "rollback_verification_checks": _rollback_verification_checks(summary, evidence_ids),
        "owners": _owners(summary, solution),
        "evidence_references": evidence_references,
    }


def render_smoke_test_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a generated smoke test plan as deterministic Markdown."""
    summary = plan.get("summary", {})
    source = plan.get("source", {})
    title = _text(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Smoke Test Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Validation plan: {_text(summary.get('validation_plan'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    _extend_section(
        lines, "User Journey Checks", plan.get("user_journey_checks") or [], _render_check
    )
    _extend_section(
        lines,
        "Deployment Verification Checks",
        plan.get("deployment_verification_checks") or [],
        _render_check,
    )
    _extend_section(
        lines, "Integration Checks", plan.get("integration_checks") or [], _render_check
    )
    _extend_section(
        lines, "Data Integrity Checks", plan.get("data_integrity_checks") or [], _render_check
    )
    _extend_section(
        lines, "Observability Checks", plan.get("observability_checks") or [], _render_check
    )
    _extend_section(
        lines,
        "Rollback Verification Checks",
        plan.get("rollback_verification_checks") or [],
        _render_check,
    )
    _extend_section(lines, "Owners", plan.get("owners") or [], _render_owner)
    _extend_section(
        lines, "Evidence References", plan.get("evidence_references") or [], _render_evidence
    )

    return "\n".join(lines).rstrip() + "\n"


def render_smoke_test_plan_csv(plan: dict[str, Any]) -> str:
    """Render a generated smoke test plan as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=SMOKE_TEST_PLAN_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(plan):
        writer.writerow(row)
    return output.getvalue()


def _user_journey_checks(
    summary: dict[str, Any], execution: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    checks = [
        _check(
            "UJ1",
            "critical_user_journey",
            "user_journey",
            f"Complete the {summary['workflow_context']} path as {summary['target_user']}.",
            summary["validation_plan"],
            "product_owner",
            ["project.workflow_context", "execution.validation_plan"],
            evidence_ids,
        ),
        _check(
            "UJ2",
            "expected_user_outcome",
            "user_journey",
            "Confirm the deployed build returns the expected user-visible result without manual repair.",
            "Primary workflow output is visible, complete, and actionable.",
            "qa_owner",
            ["project.value_proposition", "execution.mvp_scope"],
            evidence_ids,
        ),
    ]
    for index, scope_item in enumerate(_list(execution.get("mvp_scope"))[:2], start=1):
        if _compact(scope_item):
            checks.append(
                _check(
                    f"UJ{index + 2}",
                    f"mvp_scope_{index}",
                    "user_journey",
                    f"Verify deployed MVP scope item: {_compact(scope_item)}.",
                    "Scope item can be exercised through the release candidate.",
                    "qa_owner",
                    ["execution.mvp_scope"],
                    evidence_ids,
                )
            )
    return checks


def _deployment_verification_checks(
    summary: dict[str, Any], solution: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _check(
            "DV1",
            "deployed_version",
            "deployment",
            "Confirm the public entry point is serving the intended release version.",
            f"Release metadata, build identifier, and stack match {summary['stack']}.",
            "release_owner",
            ["solution.suggested_stack", "solution.technical_approach"],
            evidence_ids,
        ),
        _check(
            "DV2",
            "configuration_baseline",
            "deployment",
            "Verify required runtime configuration, secrets, feature flags, and environment values are present.",
            _compact(solution.get("technical_approach"))
            or "Runtime configuration is present for the primary workflow.",
            "engineering_owner",
            ["solution.technical_approach", "solution.composability_notes"],
            evidence_ids,
        ),
    ]


def _integration_checks(
    summary: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    checks = [
        _check(
            "IN1",
            "external_dependency_round_trip",
            "integration",
            "Exercise each required external API, datastore, queue, model provider, or platform integration.",
            "Dependencies respond successfully with production-safe test data.",
            "engineering_owner",
            ["solution.suggested_stack", "solution.composability_notes"],
            evidence_ids,
        ),
        _check(
            "IN2",
            "integration_failure_path",
            "integration",
            f"Trigger a controlled dependency failure during {summary['workflow_context']}.",
            "Failure path is classified, surfaced to the user or operator, and does not corrupt state.",
            "on_call_owner",
            ["execution.risks"],
            evidence_ids,
        ),
    ]
    if _compact(solution.get("composability_notes")):
        checks.append(
            _check(
                "IN3",
                "composability_contract",
                "integration",
                f"Verify composability contract: {_compact(solution.get('composability_notes'))}.",
                "Downstream handoff or adapter behavior matches the spec notes.",
                "engineering_owner",
                ["solution.composability_notes"],
                evidence_ids,
            )
        )
    elif _list(execution.get("risks")):
        checks.append(
            _check(
                "IN3",
                "known_integration_risk",
                "integration",
                f"Confirm mitigation for known launch risk: {_compact(_list(execution.get('risks'))[0])}.",
                "Risk has an accepted mitigation or rollback trigger before rollout expands.",
                "launch_owner",
                ["execution.risks"],
                evidence_ids,
            )
        )
    return checks


def _data_integrity_checks(
    summary: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _check(
            "DI1",
            "state_before_after",
            "data_integrity",
            f"Compare records, files, jobs, and side effects before and after {summary['workflow_context']}.",
            "No unexpected creates, updates, deletes, duplicates, or orphaned work items appear.",
            "data_owner",
            ["project.workflow_context", "execution.mvp_scope"],
            evidence_ids,
        ),
        _check(
            "DI2",
            "idempotency_and_replay",
            "data_integrity",
            "Repeat the smoke workflow with the same safe fixture or account.",
            "Repeated execution is idempotent or produces a documented, reversible duplicate-safe result.",
            "data_owner",
            ["execution.validation_plan"],
            evidence_ids,
        ),
    ]


def _observability_checks(
    summary: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _check(
            "OB1",
            "workflow_telemetry",
            "observability",
            f"Confirm success, failure, and latency telemetry emits for {summary['workflow_context']}.",
            "Metrics, logs, and traces include a release identifier and workflow stage.",
            "engineering_owner",
            ["observability_plan", "project.workflow_context"],
            evidence_ids,
        ),
        _check(
            "OB2",
            "alert_and_dashboard_visibility",
            "observability",
            "Verify dashboards and alert routes show the smoke run within the expected measurement window.",
            "On-call and launch owners can see the result without querying raw production data.",
            "on_call_owner",
            ["observability_plan", "slo_plan"],
            evidence_ids,
        ),
    ]


def _rollback_verification_checks(
    summary: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _check(
            "RB1",
            "rollback_switch_ready",
            "rollback",
            "Confirm the rollback switch, previous artifact, feature flag, or traffic control is ready.",
            "Release owner can identify the exact command or control needed to stop exposure.",
            "release_owner",
            ["rollback_plan"],
            evidence_ids,
        ),
        _check(
            "RB2",
            "post_rollback_workflow_check",
            "rollback",
            f"Verify the {summary['workflow_context']} path remains testable after rollback or exposure pause.",
            "Known-good behavior can be restored and re-smoked with the same fixture.",
            "qa_owner",
            ["rollback_plan", "execution.validation_plan"],
            evidence_ids,
        ),
    ]


def _owners(summary: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "OWN1",
            "role": "product_owner",
            "suggested_owner": summary["buyer"],
            "responsibility": "Owns user journey acceptance and launch go/no-go evidence.",
        },
        {
            "id": "OWN2",
            "role": "engineering_owner",
            "suggested_owner": _engineering_owner(solution),
            "responsibility": "Owns deploy, integration, telemetry, and runtime configuration checks.",
        },
        {
            "id": "OWN3",
            "role": "data_owner",
            "suggested_owner": "data or service owner",
            "responsibility": "Owns data integrity verification and replay or quarantine decisions.",
        },
        {
            "id": "OWN4",
            "role": "on_call_owner",
            "suggested_owner": "release engineer or service owner",
            "responsibility": "Owns alert visibility, escalation, and operational triage.",
        },
        {
            "id": "OWN5",
            "role": "release_owner",
            "suggested_owner": "release coordinator",
            "responsibility": "Owns deployment verification, rollback readiness, and smoke test completion.",
        },
        {
            "id": "OWN6",
            "role": "qa_owner",
            "suggested_owner": summary["target_user"],
            "responsibility": "Owns repeatable smoke fixtures and pass/fail recording.",
        },
    ]


def _check(
    check_id: str,
    name: str,
    category: str,
    description: str,
    expected_result: str,
    owner: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "category": category,
        "description": _compact(description),
        "expected_result": _compact(expected_result),
        "owner": owner,
        "status": "pending",
        "derived_from": [item for item in derived_from if _compact(item)],
        "evidence_reference_ids": evidence_ids,
    }


def _evidence_references(spec: dict[str, Any]) -> list[dict[str, str]]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    references: list[dict[str, str]] = []
    for insight_id in _list(evidence.get("insight_ids")):
        if _compact(insight_id):
            references.append(
                {
                    "id": f"insight:{insight_id}",
                    "type": "insight",
                    "summary": "Source insight attached to the TactSpec preview.",
                }
            )
    for signal_id in _list(evidence.get("signal_ids")):
        if _compact(signal_id):
            references.append(
                {
                    "id": f"signal:{signal_id}",
                    "type": "signal",
                    "summary": "Evidence signal attached to the TactSpec preview.",
                }
            )
    for idea_id in _list(evidence.get("source_idea_ids")):
        if _compact(idea_id):
            references.append(
                {
                    "id": f"idea:{idea_id}",
                    "type": "source_idea",
                    "summary": "Source idea linked to the TactSpec preview.",
                }
            )
    if _compact(evidence.get("rationale")):
        references.append(
            {
                "id": "spec:evidence_rationale",
                "type": "rationale",
                "summary": _compact(evidence.get("rationale")),
            }
        )
    if not references:
        references.append(
            {
                "id": "spec:fallback",
                "type": "fallback",
                "summary": "No evidence references were provided; smoke test checks use conservative release verification defaults.",
            }
        )
    return _dedupe_by_id(references)


def _workflow(project: dict[str, Any], execution: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _first_string(execution.get("mvp_scope"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
    return "unspecified"


def _engineering_owner(solution: dict[str, Any]) -> str:
    stack = solution.get("suggested_stack")
    if isinstance(stack, dict) and stack:
        language = _compact(stack.get("language"))
        framework = _compact(stack.get("framework"))
        runtime = _compact(stack.get("runtime"))
        label = " / ".join(item for item in (language, framework, runtime) if item)
        if label:
            return f"{label} service owner"
    return "service owner"


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_check(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Check: {_text(item.get('description'))}",
        f"- Expected result: {_text(item.get('expected_result'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Type: {_text(item.get('type'))}",
        f"- Summary: {_text(item.get('summary'))}",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    rows = [
        _csv_row(
            plan,
            section="summary",
            type_="summary",
            item_id="summary",
            status=summary.get("recommendation"),
            description=summary.get("validation_plan"),
            evidence_reference_ids=[
                item.get("id") for item in _dict_items(plan.get("evidence_references"))
            ],
        )
    ]

    for section in (
        "user_journey_checks",
        "deployment_verification_checks",
        "integration_checks",
        "data_integrity_checks",
        "observability_checks",
        "rollback_verification_checks",
    ):
        for item in _dict_items(plan.get(section)):
            rows.append(
                _csv_row(
                    plan,
                    section=section,
                    type_="check",
                    item_id=item.get("id"),
                    name=item.get("name"),
                    category=item.get("category"),
                    status=item.get("status"),
                    owner=item.get("owner"),
                    description=item.get("description"),
                    expected_result=item.get("expected_result"),
                    derived_from=item.get("derived_from"),
                    evidence_reference_ids=item.get("evidence_reference_ids"),
                )
            )

    for item in _dict_items(plan.get("owners")):
        rows.append(
            _csv_row(
                plan,
                section="owners",
                type_="owner",
                item_id=item.get("id"),
                name=item.get("role"),
                owner=item.get("role"),
                suggested_owner=item.get("suggested_owner"),
                responsibility=item.get("responsibility"),
            )
        )

    for item in _dict_items(plan.get("evidence_references")):
        rows.append(
            _csv_row(
                plan,
                section="evidence_references",
                type_="evidence",
                item_id=item.get("id"),
                name=item.get("id"),
                evidence_reference_ids=[item.get("id")],
                evidence_type=item.get("type"),
                evidence_summary=item.get("summary"),
            )
        )

    return rows


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    type_: str,
    item_id: Any = None,
    name: Any = None,
    category: Any = None,
    status: Any = None,
    owner: Any = None,
    suggested_owner: Any = None,
    responsibility: Any = None,
    description: Any = None,
    expected_result: Any = None,
    derived_from: Any = None,
    evidence_reference_ids: Any = None,
    evidence_type: Any = None,
    evidence_summary: Any = None,
) -> dict[str, str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "source_status": source.get("status"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "title": summary.get("title"),
        "workflow_context": summary.get("workflow_context"),
        "target_user": summary.get("target_user"),
        "buyer": summary.get("buyer"),
        "stack": summary.get("stack"),
        "validation_plan": summary.get("validation_plan"),
        "recommendation": summary.get("recommendation"),
        "overall_score": summary.get("overall_score"),
        "item_id": item_id,
        "name": name,
        "category": category,
        "status": status,
        "owner": owner,
        "suggested_owner": suggested_owner,
        "responsibility": responsibility,
        "description": description,
        "expected_result": expected_result,
        "derived_from": derived_from,
        "evidence_reference_ids": evidence_reference_ids,
        "evidence_type": evidence_type,
        "evidence_summary": evidence_summary,
    }
    return {column: _csv_text(values.get(column)) for column in SMOKE_TEST_PLAN_CSV_COLUMNS}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}={_csv_text(item)}"
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


def _first_string(value: Any) -> str:
    for item in _list(value):
        text = _compact(item)
        if text:
            return text
    return ""


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dedupe_by_id(references: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for reference in references:
        deduped.setdefault(reference["id"], reference)
    return list(deduped.values())


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
