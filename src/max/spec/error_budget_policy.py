"""Generate deterministic error budget policies for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


ERROR_BUDGET_POLICY_SCHEMA_VERSION = "max-error-budget-policy/v1"
KIND = "max.error_budget_policy"
ERROR_BUDGET_POLICY_CSV_COLUMNS = (
    "section",
    "type",
    "source_id",
    "title",
    "strictness",
    "item_id",
    "name",
    "target",
    "window",
    "severity",
    "owner",
    "condition",
    "action",
    "references",
    "evidence_refs",
)


def generate_error_budget_policy(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic reliability governance."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    context = _context(spec)
    slo_candidates = _slo_candidates(context)
    budget_windows = _budget_windows(context)
    burn_rate_alerts = _burn_rate_alerts(context)
    release_gates = _release_gates(context)
    freeze_criteria = _freeze_criteria(context)
    owner_actions = _owner_actions(context)

    return {
        "schema_version": ERROR_BUDGET_POLICY_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": {
            "title": context["title"],
            "workflow_context": context["workflow_context"],
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "evaluation_score": context["evaluation_score"],
            "recommendation": context["recommendation"],
            "risk_level": context["risk_level"],
            "strictness": context["strictness"],
            "acceptance_criteria_count": len(context["acceptance_criteria"]),
            "suggested_stack": context["stack_label"],
        },
        "slo_candidates": slo_candidates,
        "budget_windows": budget_windows,
        "burn_rate_alerts": burn_rate_alerts,
        "release_gates": release_gates,
        "freeze_criteria": freeze_criteria,
        "owner_actions": owner_actions,
        "evidence_references": context["evidence_references"],
    }


def render_error_budget_policy_markdown(policy: dict[str, Any]) -> str:
    """Render an error budget policy as deterministic Markdown."""
    summary = policy.get("summary") if isinstance(policy.get("summary"), dict) else {}
    source = policy.get("source") if isinstance(policy.get("source"), dict) else {}
    title = _text(summary.get("title")) or _text(source.get("idea_id")) or "TactSpec"

    lines = [
        f"# {title} Error Budget Policy",
        "",
        f"- Schema version: {_text(policy.get('schema_version'))}",
        f"- Kind: {_text(policy.get('kind'))}",
        f"- Source ID: {_source_id(source)}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Evaluation score: {_text(summary.get('evaluation_score')) or 'none'}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Risk level: {_text(summary.get('risk_level'))}",
        f"- Strictness: {_text(summary.get('strictness'))}",
        f"- Suggested stack: {_text(summary.get('suggested_stack')) or 'none'}",
        "",
    ]

    _extend_section(lines, "SLO Candidates", policy.get("slo_candidates") or [], _render_slo)
    _extend_section(lines, "Budget Windows", policy.get("budget_windows") or [], _render_window)
    _extend_section(lines, "Burn-Rate Alerts", policy.get("burn_rate_alerts") or [], _render_alert)
    _extend_section(lines, "Release Gates", policy.get("release_gates") or [], _render_gate)
    _extend_section(lines, "Freeze Criteria", policy.get("freeze_criteria") or [], _render_freeze)
    _extend_section(lines, "Owner Actions", policy.get("owner_actions") or [], _render_owner_action)
    _extend_section(lines, "Evidence References", policy.get("evidence_references") or [], _render_evidence)

    return "\n".join(lines).rstrip() + "\n"


def render_error_budget_policy_csv(policy: dict[str, Any]) -> str:
    """Render an error budget policy as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=ERROR_BUDGET_POLICY_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(policy if isinstance(policy, dict) else {}):
        writer.writerow(row)
    return output.getvalue()


def _context(spec: dict[str, Any]) -> dict[str, Any]:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}

    risks = _string_list(execution.get("risks"))
    acceptance_criteria = _acceptance_criteria(spec)
    evaluation_score = _number(evaluation.get("overall_score"))
    recommendation = _compact(evaluation.get("recommendation"))
    risk_level = _risk_level(risks, evaluation_score, recommendation)
    strictness = "strict" if risk_level == "high" else "standard"
    evidence_references = _evidence_references(spec)
    stack = solution.get("suggested_stack") if isinstance(solution.get("suggested_stack"), dict) else {}

    return {
        "source": {
            "system": _compact(source.get("system")) or "max",
            "type": _compact(source.get("type")) or "tact_spec",
            "idea_id": _compact(source.get("idea_id")),
            "status": _compact(source.get("status")),
            "domain": _compact(source.get("domain")),
            "category": _compact(source.get("category")),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(evidence_references),
        },
        "title": _compact(project.get("title")) or "Untitled TactSpec",
        "summary": _compact(project.get("summary")),
        "workflow_context": _compact(project.get("workflow_context")) or "primary workflow",
        "target_user": _compact(project.get("specific_user") or project.get("target_users")) or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "validation_plan": _compact(execution.get("validation_plan")) or "repeatable release validation",
        "mvp_scope": _string_list(execution.get("mvp_scope")),
        "risks": risks,
        "acceptance_criteria": acceptance_criteria,
        "evaluation_score": evaluation_score,
        "recommendation": recommendation or None,
        "risk_level": risk_level,
        "strictness": strictness,
        "stack_label": _stack_label(stack),
        "is_fast_feedback": _contains_any(
            " ".join(
                [
                    _compact(solution.get("technical_approach")),
                    _stack_label(stack),
                    _compact(project.get("workflow_context")),
                ]
            ),
            ("api", "cli", "ci", "realtime", "real-time", "webhook", "queue"),
        ),
        "evidence_references": evidence_references,
    }


def _slo_candidates(context: dict[str, Any]) -> list[dict[str, Any]]:
    strict = context["strictness"] == "strict"
    latency = "p95 <= 1000 ms" if strict and context["is_fast_feedback"] else "p95 <= 1500 ms" if context["is_fast_feedback"] else "p95 <= 2500 ms"
    availability = "99.5% during staffed pilot windows" if strict else "99.0% during pilot; 99.5% after launch"
    criteria = context["acceptance_criteria"][0] if context["acceptance_criteria"] else context["validation_plan"]
    return [
        _item(
            "SLO1",
            "workflow_availability",
            f"{context['workflow_context']} is reachable for {context['target_user']}.",
            "availability",
            availability,
            "rolling 7 days during pilot, rolling 30 days after launch",
            "on_call_owner",
            ["project.workflow_context", "execution.validation_plan"],
        ),
        _item(
            "SLO2",
            "workflow_latency",
            f"User-visible response time for {context['workflow_context']}.",
            "latency",
            latency,
            "rolling 24 hours",
            "technical_owner",
            ["solution.technical_approach", "solution.suggested_stack"],
        ),
        _item(
            "SLO3",
            "acceptance_pass_rate",
            f"Release candidate continues to satisfy acceptance expectation: {criteria}.",
            "quality",
            "100% launch-critical criteria pass" if strict else ">= 95% acceptance criteria pass",
            "per release candidate",
            "qa_owner",
            ["acceptance_criteria", "execution.validation_plan"],
        ),
        _item(
            "SLO4",
            "known_risk_escape_rate",
            "Known launch risks do not become unresolved user-visible failures.",
            "risk",
            "0 unresolved critical escapes" if strict else "<= 1 accepted non-critical escape",
            "per release window",
            "launch_owner",
            ["execution.risks", "evaluation.overall_score"],
        ),
    ]


def _budget_windows(context: dict[str, Any]) -> list[dict[str, Any]]:
    if context["strictness"] == "strict":
        return [
            _window("BW1", "validation", "24 hours before release", "0 critical SLO misses", "qa_owner"),
            _window("BW2", "staffed_pilot", "rolling 7 days", "0.25% workflow failure budget", "on_call_owner"),
            _window("BW3", "post_launch", "rolling 30 days", "0.5% workflow failure budget", "launch_owner"),
        ]
    return [
        _window("BW1", "staffed_pilot", "rolling 7 days", "1.0% workflow failure budget", "on_call_owner"),
        _window("BW2", "post_launch", "rolling 30 days", "0.5% workflow failure budget", "launch_owner"),
    ]


def _burn_rate_alerts(context: dict[str, Any]) -> list[dict[str, Any]]:
    if context["strictness"] == "strict":
        alerts = [
            _alert("BRA1", "fast_burn", "critical", "Error budget burns faster than 2x expected rate for 30 minutes.", "Page on_call_owner and pause rollout expansion.", "on_call_owner", ["SLO1", "BW2"]),
            _alert("BRA2", "slow_burn", "high", "Error budget burns faster than 1x expected rate for 2 hours.", "Open launch review and require mitigation owner before the next release.", "launch_owner", ["SLO1", "BW2", "BW3"]),
            _alert("BRA3", "acceptance_regression", "critical", "Any launch-critical acceptance criterion fails after one retry.", "Block release and attach failed criterion evidence to the go/no-go record.", "qa_owner", ["SLO3", "acceptance_criteria"]),
        ]
    else:
        alerts = [
            _alert("BRA1", "fast_burn", "critical", "Error budget burns faster than 5x expected rate for 1 hour.", "Page on_call_owner and pause rollout expansion.", "on_call_owner", ["SLO1", "BW1"]),
            _alert("BRA2", "slow_burn", "high", "Error budget burns faster than 2x expected rate for 6 hours.", "Review recent releases, risks, and dependency health.", "launch_owner", ["SLO1", "BW1", "BW2"]),
            _alert("BRA3", "acceptance_regression", "high", "Acceptance pass rate falls below the release gate threshold.", "Hold non-critical release until failing criteria are triaged.", "qa_owner", ["SLO3", "acceptance_criteria"]),
        ]
    if context["risks"]:
        alerts.append(
            _alert("BRA4", "known_risk_materialized", "critical", f"Known risk appears in telemetry or support intake: {context['risks'][0]}.", "Escalate to launch_owner for mitigation, acceptance, or freeze decision.", "launch_owner", ["execution.risks", "SLO4"])
        )
    return alerts


def _release_gates(context: dict[str, Any]) -> list[dict[str, Any]]:
    strict = context["strictness"] == "strict"
    return [
        _gate("RG1", "instrumentation_complete", "All SLO candidates have dashboards, alert routes, and owners.", "technical_owner", "required", ["slo_candidates"]),
        _gate("RG2", "acceptance_clean", "Launch-critical acceptance criteria pass in the release candidate.", "qa_owner", "required", ["acceptance_criteria", "SLO3"]),
        _gate("RG3", "risk_disposition", "Known risks have mitigation, explicit acceptance, or rollback handling.", "launch_owner", "required" if strict else "recommended", ["execution.risks", "SLO4"]),
        _gate("RG4", "budget_health", "No critical burn-rate alert is open and projected budget exhaustion is below threshold.", "on_call_owner", "required", ["burn_rate_alerts", "budget_windows"]),
        _gate("RG5", "sponsor_approval", f"{context['buyer']} approves any exception with owner and expiry recorded.", "product_owner", "required" if strict else "exception_only", ["project.buyer", "summary.strictness"]),
    ]


def _freeze_criteria(context: dict[str, Any]) -> list[dict[str, Any]]:
    if context["strictness"] == "strict":
        return [
            _freeze("FC1", "budget_warning", "25% of pilot budget consumed before midpoint.", "Freeze rollout expansion until mitigation is accepted.", "launch_owner", ["BW2"]),
            _freeze("FC2", "budget_exhausted", "50% of pilot budget consumed or any critical alert remains open.", "Freeze non-critical changes and require sponsor exception for release.", "launch_owner", ["BW2", "BRA1"]),
            _freeze("FC3", "quality_regression", "Any launch-critical acceptance criterion fails in validation.", "Block release until the failed criterion passes in a rerun.", "qa_owner", ["SLO3", "RG2"]),
        ]
    return [
        _freeze("FC1", "budget_warning", "50% of pilot budget consumed before midpoint.", "Review recent changes and open risks before expansion.", "launch_owner", ["BW1"]),
        _freeze("FC2", "budget_exhausted", "75% of pilot budget consumed or a critical alert remains open.", "Freeze non-critical rollout until budget health recovers.", "launch_owner", ["BW1", "BRA1"]),
        _freeze("FC3", "quality_regression", "Acceptance pass rate falls below release gate threshold.", "Hold release until failing criteria are triaged.", "qa_owner", ["SLO3", "RG2"]),
    ]


def _owner_actions(context: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        _owner_action("OA1", "technical_owner", "Instrument workflow availability, latency, and acceptance pass-rate metrics.", "before pilot", ["SLO1", "SLO2", "SLO3"]),
        _owner_action("OA2", "on_call_owner", "Configure burn-rate alerts and verify routing with a test notification.", "before pilot", ["burn_rate_alerts"]),
        _owner_action("OA3", "qa_owner", f"Run validation path: {context['validation_plan']}.", "release candidate", ["execution.validation_plan", "acceptance_criteria"]),
        _owner_action("OA4", "launch_owner", "Review budget consumption, open risks, and freeze criteria at go/no-go.", "go/no-go", ["budget_windows", "freeze_criteria"]),
    ]
    if context["strictness"] == "strict":
        actions.append(
            _owner_action("OA5", "product_owner", "Record sponsor approval for any exception before release expansion.", "before expansion", ["RG5", "summary.buyer"])
        )
    return actions


def _item(item_id: str, name: str, description: str, category: str, target: str, window: str, owner: str, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "description": description, "category": category, "target": target, "window": window, "owner": owner, "references": references}


def _window(item_id: str, name: str, window: str, budget: str, owner: str) -> dict[str, Any]:
    return {"id": item_id, "name": name, "window": window, "budget": budget, "owner": owner}


def _alert(item_id: str, name: str, severity: str, condition: str, action: str, owner: str, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "severity": severity, "condition": condition, "action": action, "owner": owner, "references": references}


def _gate(item_id: str, name: str, condition: str, owner: str, status: str, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "condition": condition, "owner": owner, "status": status, "references": references}


def _freeze(item_id: str, name: str, condition: str, action: str, owner: str, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "condition": condition, "action": action, "owner": owner, "references": references}


def _owner_action(item_id: str, owner: str, action: str, timing: str, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "owner": owner, "action": action, "timing": timing, "references": references}


def _render_slo(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Category: {item['category']}", f"- Description: {item['description']}", f"- Target: {item['target']}", f"- Window: {item['window']}", f"- Owner: {item['owner']}", f"- References: {_join(item.get('references'))}"]


def _render_window(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Window: {item['window']}", f"- Budget: {item['budget']}", f"- Owner: {item['owner']}"]


def _render_alert(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']} ({item['severity']})", "", f"- Condition: {item['condition']}", f"- Action: {item['action']}", f"- Owner: {item['owner']}", f"- References: {_join(item.get('references'))}"]


def _render_gate(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Condition: {item['condition']}", f"- Owner: {item['owner']}", f"- Status: {item['status']}", f"- References: {_join(item.get('references'))}"]


def _render_freeze(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Condition: {item['condition']}", f"- Action: {item['action']}", f"- Owner: {item['owner']}", f"- References: {_join(item.get('references'))}"]


def _render_owner_action(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['owner']}", "", f"- Action: {item['action']}", f"- Timing: {item['timing']}", f"- References: {_join(item.get('references'))}"]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Type: {item['type']}", f"- Reference: {item['reference']}"]


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _csv_rows(policy: dict[str, Any]) -> list[dict[str, str]]:
    source = policy.get("source") if isinstance(policy.get("source"), dict) else {}
    summary = policy.get("summary") if isinstance(policy.get("summary"), dict) else {}
    base = {"source_id": _source_id(source), "title": summary.get("title"), "strictness": summary.get("strictness"), "evidence_refs": [item.get("reference") for item in policy.get("evidence_references") or [] if isinstance(item, dict)]}
    rows: list[dict[str, str]] = []
    for item in policy.get("slo_candidates") or []:
        rows.append(_csv_row(**base, section="slo_candidates", type=item.get("category"), item_id=item.get("id"), name=item.get("name"), target=item.get("target"), window=item.get("window"), owner=item.get("owner"), condition=item.get("description"), references=item.get("references")))
    for item in policy.get("budget_windows") or []:
        rows.append(_csv_row(**base, section="budget_windows", type="budget_window", item_id=item.get("id"), name=item.get("name"), target=item.get("budget"), window=item.get("window"), owner=item.get("owner")))
    for item in policy.get("burn_rate_alerts") or []:
        rows.append(_csv_row(**base, section="burn_rate_alerts", type="alert", item_id=item.get("id"), name=item.get("name"), severity=item.get("severity"), owner=item.get("owner"), condition=item.get("condition"), action=item.get("action"), references=item.get("references")))
    for item in policy.get("release_gates") or []:
        rows.append(_csv_row(**base, section="release_gates", type=item.get("status"), item_id=item.get("id"), name=item.get("name"), owner=item.get("owner"), condition=item.get("condition"), references=item.get("references")))
    for item in policy.get("freeze_criteria") or []:
        rows.append(_csv_row(**base, section="freeze_criteria", type="freeze", item_id=item.get("id"), name=item.get("name"), owner=item.get("owner"), condition=item.get("condition"), action=item.get("action"), references=item.get("references")))
    for item in policy.get("owner_actions") or []:
        rows.append(_csv_row(**base, section="owner_actions", type="owner_action", item_id=item.get("id"), owner=item.get("owner"), window=item.get("timing"), action=item.get("action"), references=item.get("references")))
    return rows


def _csv_row(**values: Any) -> dict[str, str]:
    return {column: _csv_text(values.get(column)) for column in ERROR_BUDGET_POLICY_CSV_COLUMNS}


def _acceptance_criteria(spec: dict[str, Any]) -> list[str]:
    criteria = spec.get("acceptance_criteria")
    if isinstance(criteria, dict):
        values = criteria.get("criteria") or criteria.get("items") or criteria.get("acceptance_criteria")
    else:
        values = criteria
    if isinstance(values, list):
        result = []
        for item in values:
            if isinstance(item, dict):
                result.append(_compact(item.get("criterion") or item.get("description") or item.get("name")))
            else:
                result.append(_compact(item))
        return [item for item in result if item]
    compact = _compact(values)
    return [compact] if compact else []


def _evidence_references(spec: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs: list[tuple[str, str]] = []
    refs.extend(("insight", item) for item in _string_list(evidence.get("insight_ids")))
    refs.extend(("signal", item) for item in _string_list(evidence.get("signal_ids")))
    refs.extend(("source_idea", item) for item in _string_list(evidence.get("source_idea_ids")))
    rationale = _compact(evidence.get("rationale"))
    if rationale:
        refs.append(("rationale", rationale))

    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for ref_type, value in refs:
        key = (ref_type, value)
        if key in seen:
            continue
        seen.add(key)
        reference = value if ref_type == "rationale" else f"{ref_type}:{value}"
        result.append({"id": f"EV{len(result) + 1}", "type": ref_type, "reference": reference})
    return result


def _risk_level(risks: list[str], score: float | None, recommendation: str) -> str:
    text = " ".join(risks).lower()
    high_terms = ("security", "privacy", "compliance", "data loss", "outage", "migration", "dependency", "protocol churn")
    if score is not None and score < 55:
        return "high"
    if recommendation in {"no", "strong_no"}:
        return "high"
    if len(risks) >= 3 or any(term in text for term in high_terms):
        return "high"
    if risks:
        return "medium"
    return "low"


def _source_id(source: dict[str, Any]) -> str:
    return _compact(source.get("idea_id")) or _compact(source.get("id")) or "tact_spec"


def _stack_label(stack: dict[str, Any]) -> str:
    parts = [f"{_compact(key)}={_compact(value)}" for key, value in sorted(stack.items()) if _compact(value)]
    return ", ".join(parts)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    compact = _compact(value)
    return [compact] if compact else []


def _join(values: Any) -> str:
    items = _string_list(values)
    return ", ".join(items) if items else "none"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    if isinstance(value, dict):
        return "; ".join(f"{_csv_text(key)}: {_csv_text(item)}" for key, item in sorted(value.items()) if _csv_text(item))
    return _compact(value)
