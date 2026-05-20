"""Generate deterministic customer acceptance test plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-customer-acceptance-test-plan/v1"
KIND = "max.spec.customer_acceptance_test_plan"


def generate_customer_acceptance_test_plan(
    unit: Any,
    evaluation: Any | None = None,
    tact_spec_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-compatible customer acceptance test plan."""
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    source = _source(unit, spec)
    risk_level = _risk_level(unit, evaluation, spec)
    scenarios = _acceptance_scenarios(unit, spec, risk_level)
    evidence = _evidence_requirements(unit, evaluation, spec, risk_level)
    gates = _sign_off_gates(unit, evaluation, spec, risk_level)
    checklist = _checklist_items(scenarios, evidence, gates)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source,
        "summary": {
            "title": source["title"],
            "target_user": _first(_field(unit, "specific_user"), _field(unit, "target_users"), "customer reviewer"),
            "buyer": _first(_field(unit, "buyer"), _nested(spec, "project", "buyer"), "customer sponsor"),
            "risk_level": risk_level,
            "scenario_count": len(scenarios),
            "evidence_requirement_count": len(evidence),
            "sign_off_gate_count": len(gates),
        },
        "acceptance_scenarios": scenarios,
        "sign_off_gates": gates,
        "evidence_requirements": evidence,
        "checklist_items": checklist,
    }


def render_customer_acceptance_test_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a customer acceptance test plan as deterministic Markdown."""
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    lines = [
        f"# {_text(summary.get('title')) or 'Customer Acceptance'} Customer Acceptance Test Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Kind: {_text(plan.get('kind'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'unknown'}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Risk level: {_text(summary.get('risk_level'))}",
        "",
    ]
    _extend(lines, "Acceptance Scenarios", plan.get("acceptance_scenarios") or [], _render_scenario)
    _extend(lines, "Evidence Requirements", plan.get("evidence_requirements") or [], _render_evidence)
    _extend(lines, "Sign-Off Gates", plan.get("sign_off_gates") or [], _render_gate)
    _extend(lines, "Checklist Items", plan.get("checklist_items") or [], _render_checklist)
    return "\n".join(lines).rstrip() + "\n"


def _acceptance_scenarios(unit: Any, spec: dict[str, Any], risk_level: str) -> list[dict[str, Any]]:
    criteria = _list_from_spec(spec, "acceptance_criteria", "criteria")
    mvp = _list_from_spec(spec, "execution", "mvp_scope")
    validation = _values(_first(_field(unit, "validation_plan"), _nested(spec, "execution", "validation_plan")))
    seeds = criteria or mvp or validation or [_first(_field(unit, "solution"), _nested(spec, "solution", "technical_approach"), "Primary workflow works for the customer")]
    result = []
    for index, item in enumerate(seeds[:5], start=1):
        name = _compact(item.get("name") or item.get("criterion") or item.get("description")) if isinstance(item, dict) else _compact(item)
        result.append(
            {
                "id": f"CAT-S{index}",
                "name": name or f"Acceptance scenario {index}",
                "actor": _first(_field(unit, "specific_user"), _nested(spec, "project", "specific_user"), "customer tester"),
                "workflow": _first(_field(unit, "workflow_context"), _nested(spec, "project", "workflow_context"), "primary workflow"),
                "pass_criteria": f"Customer confirms '{name or 'the scenario'}' without unresolved severity-1 or severity-2 defects.",
                "fail_criteria": "Customer cannot complete the workflow, required evidence is missing, or a critical risk remains open.",
                "severity": "high" if risk_level == "high" and index == 1 else "medium",
            }
        )
    return result


def _evidence_requirements(unit: Any, evaluation: Any | None, spec: dict[str, Any], risk_level: str) -> list[dict[str, Any]]:
    refs = _values(_field(unit, "evidence_rationale")) + _list_from_spec(spec, "evidence", "rationale")
    weaknesses = _values(_field(evaluation, "weaknesses"))
    risks = _values(_field(unit, "domain_risks")) + _list_from_spec(spec, "execution", "risks")
    seeds = refs or ["Customer test notes and annotated screenshots"]
    if weaknesses or risks or risk_level == "high":
        seeds.extend((weaknesses or risks or ["High-risk acceptance decision"])[:2])
    result = []
    for index, item in enumerate(_dedupe(seeds)[:5], start=1):
        result.append(
            {
                "id": f"CAT-E{index}",
                "type": "risk_evidence" if index > 1 and risk_level == "high" else "acceptance_evidence",
                "description": item,
                "required_from": _first(_field(unit, "buyer"), "customer sponsor"),
                "storage_expectation": "Attach to the customer acceptance record before sign-off.",
            }
        )
    return result


def _sign_off_gates(unit: Any, evaluation: Any | None, spec: dict[str, Any], risk_level: str) -> list[dict[str, Any]]:
    approvers = _dedupe(
        [
            _first(_field(unit, "buyer"), _nested(spec, "project", "buyer"), "customer sponsor"),
            _first(_field(unit, "specific_user"), _nested(spec, "project", "specific_user"), "customer operations owner"),
            "delivery owner",
        ]
    )
    if risk_level == "high":
        approvers.append("risk owner")
    recommendation = _compact(_field(evaluation, "recommendation")) or "not evaluated"
    return [
        {
            "id": f"CAT-G{index}",
            "name": f"{approver} sign-off",
            "approver": approver,
            "condition": "All acceptance scenarios pass and required evidence is attached.",
            "blocking": risk_level == "high" or approver in approvers[:2],
            "evaluation_context": recommendation,
        }
        for index, approver in enumerate(_dedupe(approvers), start=1)
    ]


def _checklist_items(scenarios: list[dict[str, Any]], evidence: list[dict[str, Any]], gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for section, items in (("acceptance_scenarios", scenarios), ("evidence_requirements", evidence), ("sign_off_gates", gates)):
        for item in items:
            rows.append({"id": f"CAT-C{len(rows) + 1}", "section": section, "source_id": item["id"], "owner": item.get("approver") or item.get("required_from") or item.get("actor"), "item": item.get("name") or item.get("description"), "done": False})
    return rows


def _risk_level(unit: Any, evaluation: Any | None, spec: dict[str, Any]) -> str:
    score = _number(_field(evaluation, "overall_score"))
    recommendation = _compact(_field(evaluation, "recommendation"))
    risks = " ".join(_values(_field(unit, "domain_risks")) + _list_from_spec(spec, "execution", "risks")).lower()
    if score is not None and score < 55 or recommendation in {"no", "strong_no"}:
        return "high"
    if any(term in risks for term in ("security", "privacy", "compliance", "blocked", "migration")):
        return "high"
    return "medium" if risks or score is not None and score < 75 else "low"


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {
        "idea_id": _first(_field(unit, "id"), source.get("idea_id"), "unknown"),
        "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled acceptance plan"),
        "domain": _first(_field(unit, "domain"), source.get("domain"), ""),
        "category": _first(_field(unit, "category"), source.get("category"), ""),
        "status": _first(_field(unit, "status"), source.get("status"), ""),
    }


def _extend(lines: list[str], title: str, items: list[dict[str, Any]], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_scenario(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Actor: {item['actor']}", f"- Workflow: {item['workflow']}", f"- Pass criteria: {item['pass_criteria']}", f"- Fail criteria: {item['fail_criteria']}"]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['type']}", "", f"- Description: {item['description']}", f"- Required from: {item['required_from']}", f"- Storage expectation: {item['storage_expectation']}"]


def _render_gate(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Approver: {item['approver']}", f"- Condition: {item['condition']}", f"- Blocking: {_text(item['blocking'])}"]


def _render_checklist(item: dict[str, Any]) -> list[str]:
    return [f"- {item['id']} [{item['section']}]: {item['item']} owner={item['owner']}"]


def _field(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _nested(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _list_from_spec(spec: dict[str, Any], section: str, key: str) -> list[str]:
    value = _nested(spec, section, key)
    return _values(value)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                result.append(_compact(item.get("name") or item.get("criterion") or item.get("description") or item.get("value")))
            else:
                result.append(_compact(item))
        return [item for item in result if item]
    compacted = _compact(value)
    return [compacted] if compacted else []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        compacted = _compact(value)
        key = compacted.casefold()
        if compacted and key not in seen:
            seen.add(key)
            result.append(compacted)
    return result


def _first(*values: Any) -> str:
    for value in values:
        compacted = _compact(value)
        if compacted:
            return compacted
    return ""


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _compact(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)
