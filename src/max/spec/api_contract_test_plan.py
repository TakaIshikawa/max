"""Generate deterministic API contract test plans for TactSpec previews."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-api-contract-test-plan/v1"
KIND = "max.api_contract_test_plan"

_ENDPOINT_KEYS = ("endpoints", "routes", "apis", "api_endpoints")
_INTEGRATION_KEYS = ("integrations", "external_services", "dependencies", "webhooks")
_DATA_MODEL_KEYS = ("data_model", "schemas", "entities", "models", "resources")


def generate_api_contract_test_plan(spec_preview: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into executable API contract test guidance."""
    spec = spec_preview if isinstance(spec_preview, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    evidence_references = _evidence_references(spec)
    evidence_ids = [reference["id"] for reference in evidence_references]
    surfaces = _contract_surfaces(spec, project, solution, execution)
    risks = [_compact(item) for item in _list(execution.get("risks")) if _compact(item)]
    weaknesses = [_compact(item) for item in _list(evaluation.get("weaknesses")) if _compact(item)]
    acceptance = _acceptance_items(spec, execution)
    test_cases = _test_cases(surfaces, acceptance, risks, weaknesses, evidence_ids)
    compatibility_checks = _compatibility_checks(surfaces, risks, weaknesses)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _compact(project.get("title"))
            or _compact(source.get("idea_id"))
            or "Untitled TactSpec",
            "source_idea_id": source.get("idea_id") or spec.get("id"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "workflow_context": _workflow(project, execution),
            "target_user": _compact(project.get("specific_user") or project.get("target_users"))
            or "primary user",
            "provider_contract_count": sum(
                1 for case in test_cases if case["contract_type"] == "provider"
            ),
            "consumer_contract_count": sum(
                1 for case in test_cases if case["contract_type"] == "consumer"
            ),
            "schema_validation_case_count": sum(
                1 for case in test_cases if case["contract_type"] == "schema_validation"
            ),
            "auth_error_case_count": sum(
                1 for case in test_cases if case["contract_type"] == "auth_error"
            ),
            "compatibility_check_count": len(compatibility_checks),
            "fallback_contracts_used": any(surface["source"] == "fallback" for surface in surfaces),
        },
        "contract_surfaces": surfaces,
        "test_cases": test_cases,
        "compatibility_checks": compatibility_checks,
        "traceability": {
            "spec_fields": _trace_fields(surfaces, acceptance, risks, weaknesses),
            "acceptance_criteria": acceptance,
            "risks": risks,
            "evaluation_weaknesses": weaknesses,
            "evidence_references": evidence_references,
        },
    }


def render_api_contract_test_plan_markdown(report: dict[str, Any]) -> str:
    """Render an API contract test plan as deterministic Markdown."""
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    title = _text(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} API Contract Test Plan",
        "",
        f"- Schema version: {_text(report.get('schema_version'))}",
        f"- Source idea ID: {_text(summary.get('source_idea_id')) or 'none'}",
        f"- TactSpec schema: {_text(summary.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Provider contracts: {_text(summary.get('provider_contract_count'))}",
        f"- Consumer contracts: {_text(summary.get('consumer_contract_count'))}",
        f"- Schema validation cases: {_text(summary.get('schema_validation_case_count'))}",
        f"- Auth and error cases: {_text(summary.get('auth_error_case_count'))}",
        f"- Compatibility checks: {_text(summary.get('compatibility_check_count'))}",
        f"- Fallback contracts used: {_text(summary.get('fallback_contracts_used'))}",
        "",
    ]

    _extend_section(
        lines, "Contract Surfaces", report.get("contract_surfaces") or [], _render_surface
    )
    _extend_section(lines, "Test Cases", report.get("test_cases") or [], _render_case)
    _extend_section(
        lines,
        "Compatibility Checks",
        report.get("compatibility_checks") or [],
        _render_compatibility_check,
    )
    _extend_traceability(lines, report.get("traceability") or {})
    return "\n".join(lines).rstrip() + "\n"


def _contract_surfaces(
    spec: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    for index, endpoint in enumerate(_surface_values(spec, solution, _ENDPOINT_KEYS), start=1):
        surfaces.append(
            _surface(
                f"SURF-E{index}",
                "endpoint",
                _surface_name(endpoint, f"endpoint_{index}"),
                _surface_description(endpoint, "Public API endpoint or route contract."),
                _surface_method(endpoint),
                ["endpoints", "solution.technical_approach"],
                "spec",
            )
        )
    for index, integration in enumerate(
        _surface_values(spec, solution, _INTEGRATION_KEYS), start=1
    ):
        surfaces.append(
            _surface(
                f"SURF-I{index}",
                "integration",
                _surface_name(integration, f"integration_{index}"),
                _surface_description(integration, "External provider or consumer integration."),
                "external",
                ["integrations", "solution.composability_notes", "solution.suggested_stack"],
                "spec",
            )
        )
    for index, model in enumerate(_surface_values(spec, solution, _DATA_MODEL_KEYS), start=1):
        surfaces.append(
            _surface(
                f"SURF-D{index}",
                "data_model",
                _surface_name(model, f"data_model_{index}"),
                _surface_description(model, "Request, response, or persisted schema contract."),
                "schema",
                ["data_model", "solution.suggested_stack"],
                "spec",
            )
        )

    if not surfaces:
        workflow = _workflow(project, execution)
        surfaces.append(
            _surface(
                "SURF-F1",
                "primary_contract",
                "primary_workflow_contract",
                f"Conservative contract for {workflow} when explicit API surfaces are not listed.",
                "unspecified",
                ["project.workflow_context", "execution.mvp_scope", "solution.technical_approach"],
                "fallback",
            )
        )
    return _dedupe_surfaces(surfaces)


def _test_cases(
    surfaces: list[dict[str, Any]],
    acceptance: list[dict[str, Any]],
    risks: list[str],
    weaknesses: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    primary = surfaces[0]
    provider_surfaces = [
        surface for surface in surfaces if surface["category"] in {"endpoint", "primary_contract"}
    ]
    consumer_surfaces = [surface for surface in surfaces if surface["category"] == "integration"]
    schema_surfaces = [surface for surface in surfaces if surface["category"] == "data_model"]

    for index, surface in enumerate(provider_surfaces or [primary], start=1):
        cases.append(
            _case(
                f"API-P{index}",
                "provider",
                surface,
                f"Provider contract returns the documented successful response for {surface['name']}.",
                "Request fixture receives a stable status, response body, and side-effect boundary.",
                ["contract_surfaces", *surface["derived_from"]],
                evidence_ids,
            )
        )
    for index, surface in enumerate(consumer_surfaces or [primary], start=1):
        cases.append(
            _case(
                f"API-C{index}",
                "consumer",
                surface,
                f"Consumer contract sends the expected request shape to {surface['name']}.",
                "Outbound payload, headers, retry behavior, and timeout handling match the contract fixture.",
                ["contract_surfaces", "solution.composability_notes"],
                evidence_ids,
            )
        )
    for index, surface in enumerate(schema_surfaces or [primary], start=1):
        cases.append(
            _case(
                f"API-S{index}",
                "schema_validation",
                surface,
                f"Schema validation accepts valid fixtures and rejects malformed input for {surface['name']}.",
                "Required fields, unknown fields, type errors, and nullability are enforced deterministically.",
                ["data_model", "execution.mvp_scope"],
                evidence_ids,
            )
        )
    cases.extend(_auth_error_cases(primary, risks, weaknesses, evidence_ids))
    for index, item in enumerate(acceptance[:3], start=1):
        cases.append(
            _case(
                f"API-A{index}",
                "acceptance_trace",
                primary,
                f"Contract fixture proves acceptance criterion: {item['statement']}",
                "The test result records pass/fail evidence against the referenced criterion.",
                item["derived_from"],
                evidence_ids,
            )
        )
    return cases


def _auth_error_cases(
    surface: dict[str, Any], risks: list[str], weaknesses: list[str], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    cases = [
        _case(
            "API-E1",
            "auth_error",
            surface,
            "Unauthenticated or missing-credential requests are rejected without side effects.",
            "Response uses the documented unauthorized error shape and records no partial mutation.",
            ["security.auth", "solution.technical_approach"],
            evidence_ids,
        ),
        _case(
            "API-E2",
            "auth_error",
            surface,
            "Invalid input and unsupported operations return stable client errors.",
            "Error payload includes a deterministic code, safe message, and no sensitive implementation detail.",
            ["acceptance_criteria", "execution.mvp_scope"],
            evidence_ids,
        ),
    ]
    if risks:
        cases.append(
            _case(
                "API-E3",
                "auth_error",
                surface,
                f"Known risk path is exercised: {risks[0]}",
                "Contract test captures the expected failure, mitigation, or explicit deferral.",
                ["execution.risks"],
                evidence_ids,
            )
        )
    if weaknesses:
        cases.append(
            _case(
                "API-E4",
                "auth_error",
                surface,
                f"Evaluation weakness is covered by a negative contract: {weaknesses[0]}",
                "The weakness is either constrained by tests or marked as an accepted contract gap.",
                ["evaluation.weaknesses"],
                evidence_ids,
            )
        )
    return cases


def _compatibility_checks(
    surfaces: list[dict[str, Any]], risks: list[str], weaknesses: list[str]
) -> list[dict[str, Any]]:
    primary = surfaces[0] if surfaces else {}
    checks = [
        _compatibility_check(
            "COMP1",
            "backward_compatible_response_shape",
            "Response fields used by current consumers remain present or have documented deprecation.",
            ["contract_surfaces", "test_cases.API-P"],
        ),
        _compatibility_check(
            "COMP2",
            "versioning_and_error_codes",
            "Status codes, error codes, and version identifiers remain stable across compatible releases.",
            ["test_cases.API-E", "summary.tact_spec_schema_version"],
        ),
        _compatibility_check(
            "COMP3",
            "consumer_fixture_replay",
            f"Existing consumer fixtures can replay against {primary.get('name') or 'the primary contract'} without contract drift.",
            ["test_cases.API-C", "solution.composability_notes"],
        ),
    ]
    if risks or weaknesses:
        checks.append(
            _compatibility_check(
                "COMP4",
                "known_gap_regression_guard",
                "Risks and evaluation weaknesses remain traceable to explicit tests, mitigations, or deferred gaps.",
                ["execution.risks", "evaluation.weaknesses"],
            )
        )
    return checks


def _acceptance_items(spec: dict[str, Any], execution: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw = spec.get("acceptance_criteria")
    if isinstance(raw, dict):
        for key in ("functional_criteria", "non_functional_criteria", "edge_cases"):
            for item in _list(raw.get(key)):
                text = _criterion_text(item)
                if text:
                    items.append(
                        _acceptance(f"AC{len(items) + 1}", text, ["acceptance_criteria", key])
                    )
    else:
        for item in _list(raw):
            text = _criterion_text(item)
            if text:
                items.append(_acceptance(f"AC{len(items) + 1}", text, ["acceptance_criteria"]))

    for scope_item in _list(execution.get("mvp_scope")):
        text = _compact(scope_item)
        if text:
            items.append(_acceptance(f"AC{len(items) + 1}", text, ["execution.mvp_scope"]))
    if _compact(execution.get("validation_plan")):
        items.append(
            _acceptance(
                f"AC{len(items) + 1}",
                _compact(execution.get("validation_plan")),
                ["execution.validation_plan"],
            )
        )
    if not items:
        items.append(
            _acceptance(
                "AC1",
                "Primary contract can be exercised with a representative success and failure fixture.",
                ["spec:fallback"],
            )
        )
    return items[:8]


def _surface_values(
    spec: dict[str, Any], solution: dict[str, Any], keys: tuple[str, ...]
) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        values.extend(_surface_entries(spec.get(key)))
        values.extend(_surface_entries(solution.get(key)))
    stack = solution.get("suggested_stack")
    if keys == _INTEGRATION_KEYS and isinstance(stack, dict):
        for key in sorted(stack):
            value = _compact(stack.get(key))
            if value:
                values.append({"name": value, "description": f"{key} stack component"})
    return [item for item in values if _surface_name(item, "")]


def _surface_entries(value: Any) -> list[Any]:
    if not isinstance(value, dict):
        return _list(value)
    if _surface_name(value, ""):
        return [value]
    entries: list[Any] = []
    for key in sorted(value):
        nested = value[key]
        if isinstance(nested, dict):
            entries.append({"name": key, **nested})
        else:
            entries.append({"name": key, "description": nested})
    return entries


def _surface(
    surface_id: str,
    category: str,
    name: str,
    description: str,
    method: str,
    derived_from: list[str],
    source: str,
) -> dict[str, Any]:
    return {
        "id": surface_id,
        "category": category,
        "name": _compact(name),
        "method": _compact(method) or "unspecified",
        "description": _compact(description),
        "source": source,
        "derived_from": [item for item in derived_from if _compact(item)],
    }


def _case(
    case_id: str,
    contract_type: str,
    surface: dict[str, Any],
    scenario: str,
    expected_result: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": case_id,
        "contract_type": contract_type,
        "surface_id": surface.get("id"),
        "surface_name": surface.get("name"),
        "scenario": _compact(scenario),
        "expected_result": _compact(expected_result),
        "fixture": f"{case_id.lower().replace('-', '_')}_fixture",
        "status": "pending",
        "derived_from": [item for item in derived_from if _compact(item)],
        "evidence_reference_ids": evidence_ids,
    }


def _compatibility_check(
    check_id: str, name: str, description: str, derived_from: list[str]
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "description": _compact(description),
        "status": "pending",
        "derived_from": derived_from,
    }


def _acceptance(item_id: str, statement: str, derived_from: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "statement": _compact(statement),
        "derived_from": derived_from,
    }


def _trace_fields(
    surfaces: list[dict[str, Any]],
    acceptance: list[dict[str, Any]],
    risks: list[str],
    weaknesses: list[str],
) -> list[str]:
    fields: list[str] = []
    for surface in surfaces:
        fields.extend(surface.get("derived_from") or [])
    for item in acceptance:
        fields.extend(item.get("derived_from") or [])
    if risks:
        fields.append("execution.risks")
    if weaknesses:
        fields.append("evaluation.weaknesses")
    return list(dict.fromkeys(item for item in fields if _compact(item)))


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
                "summary": "No evidence references were provided; contract tests use conservative traceability defaults.",
            }
        )
    return _dedupe_by_id(references)


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _extend_traceability(lines: list[str], traceability: dict[str, Any]) -> None:
    lines.extend(["## Evidence Traceability", ""])
    lines.append(f"- Spec fields: {_join_code(traceability.get('spec_fields'))}")
    lines.append(f"- Risks: {_join_text(traceability.get('risks'))}")
    lines.append(
        f"- Evaluation weaknesses: {_join_text(traceability.get('evaluation_weaknesses'))}"
    )
    lines.append("")
    _extend_section(
        lines,
        "Traceable Acceptance Criteria",
        traceability.get("acceptance_criteria") or [],
        _render_acceptance,
    )
    _extend_section(
        lines,
        "Evidence References",
        traceability.get("evidence_references") or [],
        _render_evidence,
    )


def _render_surface(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Method: {_text(item.get('method'))}",
        f"- Source: {_text(item.get('source'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_case(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('contract_type'))}",
        f"- Surface: `{_text(item.get('surface_id'))}` {_text(item.get('surface_name'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Scenario: {_text(item.get('scenario'))}",
        f"- Expected result: {_text(item.get('expected_result'))}",
        f"- Fixture: `{_text(item.get('fixture'))}`",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_compatibility_check(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Check: {_text(item.get('description'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_acceptance(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Statement: {_text(item.get('statement'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Type: {_text(item.get('type'))}",
        f"- Summary: {_text(item.get('summary'))}",
    ]


def _surface_name(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        for key in ("name", "path", "route", "endpoint", "resource", "service", "id", "title"):
            text = _compact(value.get(key))
            if text:
                return text
        return fallback
    return _compact(value) or fallback


def _surface_description(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        for key in ("description", "summary", "contract", "purpose"):
            text = _compact(value.get(key))
            if text:
                return text
    return fallback


def _surface_method(value: Any) -> str:
    if isinstance(value, dict):
        return _compact(value.get("method") or value.get("verb")) or "HTTP"
    text = _compact(value).upper()
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        if method in text:
            return method
    return "HTTP"


def _criterion_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("statement", "description", "criteria", "title", "name"):
            text = _compact(value.get(key))
            if text:
                return text
    return _compact(value)


def _workflow(project: dict[str, Any], execution: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _first_string(execution.get("mvp_scope"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _dedupe_surfaces(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for surface in surfaces:
        deduped.setdefault((surface["category"], surface["name"].lower()), surface)
    return list(deduped.values())


def _dedupe_by_id(references: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for reference in references:
        deduped.setdefault(reference["id"], reference)
    return list(deduped.values())


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _join_text(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    return "; ".join(items) if items else "none"


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
    if isinstance(value, set):
        return sorted(value)
    return [value]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
