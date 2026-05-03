"""Generate deterministic release readiness gates for TactSpec previews."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any


RELEASE_READINESS_GATE_SCHEMA_VERSION = "max-release-readiness-gate/v1"
RELEASE_READINESS_GATE_CSV_COLUMNS = (
    "section",
    "type",
    "source_system",
    "source_type",
    "source_idea_id",
    "source_status",
    "source_domain",
    "source_category",
    "tact_spec_schema_version",
    "title",
    "decision",
    "go",
    "workflow_context",
    "target_user",
    "buyer",
    "recommendation",
    "overall_score",
    "item_id",
    "dimension_id",
    "name",
    "status",
    "required",
    "owner",
    "evidence",
    "blocker_risk",
    "next_action",
)

_DIMENSIONS = (
    "scope",
    "implementation",
    "security",
    "observability",
    "rollback",
    "support",
    "launch_evidence",
)


def generate_release_readiness_gate(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into a deterministic go/no-go release gate."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    artifacts = spec.get("artifacts") if isinstance(spec.get("artifacts"), dict) else {}

    dimensions = [
        _scope_dimension(project, execution),
        _implementation_dimension(solution, execution, spec),
        _security_dimension(spec, artifacts),
        _observability_dimension(spec, artifacts),
        _rollback_dimension(spec, artifacts),
        _support_dimension(project, execution, artifacts),
        _launch_evidence_dimension(spec, evaluation, artifacts),
    ]
    blockers = _blockers(dimensions, evaluation)
    decision = "go" if not blockers else "no-go"

    return {
        "schema_version": RELEASE_READINESS_GATE_SCHEMA_VERSION,
        "kind": "max.release_readiness_gate",
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
            "title": _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec",
            "decision": decision,
            "go": decision == "go",
            "target_user": _compact(project.get("specific_user") or project.get("target_users"))
            or "primary user",
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "workflow_context": _workflow(project),
            "recommendation": evaluation.get("recommendation") if evaluation else None,
            "overall_score": evaluation.get("overall_score") if evaluation else None,
            "ready_dimension_count": sum(1 for dimension in dimensions if dimension["status"] == "ready"),
            "blocker_count": len(blockers),
        },
        "readiness_dimensions": dimensions,
        "blockers": blockers,
        "required_signoffs": _required_signoffs(decision, dimensions, project),
    }


def render_release_readiness_gate_markdown(gate: dict[str, Any]) -> str:
    """Render a generated release readiness gate as a stable Markdown document."""
    summary = gate.get("summary", {})
    source = gate.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Release Readiness Gate",
        "",
        f"- Schema version: {_text(gate.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Decision: {_text(summary.get('decision'))}",
        f"- Go: {_text(summary.get('go'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        f"- Ready dimensions: {_text(summary.get('ready_dimension_count'))}/{len(_DIMENSIONS)}",
        f"- Blockers: {_text(summary.get('blocker_count'))}",
        "",
    ]

    _extend_section(
        lines,
        "Readiness Dimensions",
        gate.get("readiness_dimensions") or [],
        _render_dimension,
    )
    _extend_section(lines, "Blockers", gate.get("blockers") or [], _render_blocker)
    _extend_section(
        lines,
        "Required Signoffs",
        gate.get("required_signoffs") or [],
        _render_signoff,
    )

    return "\n".join(lines).rstrip() + "\n"


def render_release_readiness_gate_csv(gate: dict[str, Any]) -> str:
    """Render a generated release readiness gate as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=RELEASE_READINESS_GATE_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(gate):
        writer.writerow(row)
    return output.getvalue()


def render_release_readiness_gate_json(gate: dict[str, Any]) -> str:
    """Render a generated release readiness gate as deterministic JSON."""
    return json.dumps(gate, indent=2, sort_keys=True) + "\n"


def _scope_dimension(project: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    evidence = _evidence(
        [
            ("project.title", project.get("title")),
            ("project.summary", project.get("summary")),
            ("project.workflow_context", project.get("workflow_context")),
            ("project.target_user", project.get("specific_user") or project.get("target_users")),
            ("execution.mvp_scope", _list(execution.get("mvp_scope"))),
        ]
    )
    missing = _missing(evidence, ["project.workflow_context", "project.target_user", "execution.mvp_scope"])
    return _dimension(
        "scope",
        "Scope",
        not missing,
        evidence,
        missing,
        "Name the target user, workflow context, and release-bounded MVP scope.",
    )


def _implementation_dimension(
    solution: dict[str, Any],
    execution: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    evidence = _evidence(
        [
            ("solution.technical_approach", solution.get("technical_approach") or solution.get("approach")),
            ("solution.suggested_stack", _stack_label(solution.get("suggested_stack"))),
            ("execution.validation_plan", execution.get("validation_plan")),
            ("acceptance_criteria", _acceptance_criteria(spec)),
        ]
    )
    missing = _missing(
        evidence,
        ["solution.technical_approach", "solution.suggested_stack", "execution.validation_plan"],
    )
    if not _acceptance_criteria(spec):
        missing.append("acceptance_criteria")
    return _dimension(
        "implementation",
        "Implementation",
        not missing,
        evidence,
        missing,
        "Attach implementation approach, concrete stack, validation plan, and acceptance criteria.",
    )


def _security_dimension(spec: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    review = artifacts.get("security_review") if isinstance(artifacts.get("security_review"), dict) else {}
    findings = _list(review.get("findings"))
    high_findings = [
        finding
        for finding in findings
        if isinstance(finding, dict) and finding.get("severity") in {"critical", "high"}
    ]
    evidence = _evidence(
        [
            ("artifacts.security_review", bool(review)),
            ("security.finding_count", review.get("summary", {}).get("finding_count") if review else None),
            ("security.high_or_critical_finding_count", len(high_findings) if review else None),
            ("security_terms", _contains_any(_haystack(spec), ("auth", "secret", "token", "permission", "tenant"))),
        ]
    )
    missing = [] if review and not high_findings else ["artifacts.security_review"]
    return _dimension(
        "security",
        "Security",
        not missing,
        evidence,
        missing,
        "Complete security review and close or explicitly waive high and critical findings.",
    )


def _observability_dimension(spec: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    plan = artifacts.get("observability_plan") if isinstance(artifacts.get("observability_plan"), dict) else {}
    evidence = _evidence(
        [
            ("artifacts.observability_plan", bool(plan)),
            ("observability.metrics", _list(plan.get("metrics"))),
            ("observability.alerts", _list(plan.get("alerts"))),
            ("observability_checks", _contains_any(_haystack(spec), ("metric", "monitor", "alert", "log", "trace"))),
        ]
    )
    missing = [] if plan and _list(plan.get("metrics")) and _list(plan.get("alerts")) else ["artifacts.observability_plan"]
    return _dimension(
        "observability",
        "Observability",
        not missing,
        evidence,
        missing,
        "Attach metrics, alerts, and rollout validation checks for the primary workflow.",
    )


def _rollback_dimension(spec: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    plan = artifacts.get("rollback_plan") if isinstance(artifacts.get("rollback_plan"), dict) else {}
    runbook = artifacts.get("operational_runbook") if isinstance(artifacts.get("operational_runbook"), dict) else {}
    evidence = _evidence(
        [
            ("artifacts.rollback_plan", bool(plan)),
            ("rollback_triggers", _list(plan.get("rollback_triggers")) or _list(runbook.get("rollback_triggers"))),
            ("rollback_terms", _contains_any(_haystack(spec), ("rollback", "feature flag", "disable", "restore"))),
        ]
    )
    missing = [] if evidence.get("rollback_triggers") else ["rollback_triggers"]
    return _dimension(
        "rollback",
        "Rollback",
        not missing,
        evidence,
        missing,
        "Provide rollback triggers, owner, and disablement or restore action before launch.",
    )


def _support_dimension(
    project: dict[str, Any],
    execution: dict[str, Any],
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    playbook = artifacts.get("support_playbook") if isinstance(artifacts.get("support_playbook"), dict) else {}
    handoff = artifacts.get("stakeholder_handoff") if isinstance(artifacts.get("stakeholder_handoff"), dict) else {}
    evidence = _evidence(
        [
            ("artifacts.support_playbook", bool(playbook)),
            ("artifacts.stakeholder_handoff", bool(handoff)),
            ("project.buyer", project.get("buyer")),
            ("execution.first_10_customers", execution.get("first_10_customers")),
        ]
    )
    missing = [] if playbook or handoff else ["support_handoff"]
    return _dimension(
        "support",
        "Support",
        not missing,
        evidence,
        missing,
        "Attach support playbook or stakeholder handoff with owner and escalation path.",
    )


def _launch_evidence_dimension(
    spec: dict[str, Any],
    evaluation: dict[str, Any],
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    launch = artifacts.get("launch_checklist") if isinstance(artifacts.get("launch_checklist"), dict) else {}
    evidence_refs = _evidence_references(spec)
    recommendation = evaluation.get("recommendation") if evaluation else None
    evidence = _evidence(
        [
            ("artifacts.launch_checklist", bool(launch)),
            ("evaluation.recommendation", recommendation),
            ("evidence.references", evidence_refs),
            ("acceptance_criteria", _acceptance_criteria(spec)),
        ]
    )
    missing = []
    if recommendation not in {"strong_yes", "yes"}:
        missing.append("evaluation.recommendation")
    if not evidence_refs:
        missing.append("evidence.references")
    if not launch:
        missing.append("artifacts.launch_checklist")
    return _dimension(
        "launch_evidence",
        "Launch Evidence",
        not missing,
        evidence,
        missing,
        "Attach launch checklist, positive evaluation recommendation, and traceable evidence references.",
    )


def _dimension(
    id_: str,
    label: str,
    ready: bool,
    evidence: dict[str, Any],
    missing: list[str],
    remediation: str,
) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "status": "ready" if ready else "blocked",
        "required": True,
        "evidence": evidence,
        "missing_evidence": missing,
        "remediation": "" if ready else remediation,
    }


def _blockers(
    dimensions: list[dict[str, Any]],
    evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers = [
        {
            "id": f"BLK{index}",
            "dimension_id": dimension["id"],
            "severity": "critical",
            "description": dimension["remediation"],
            "missing_evidence": dimension["missing_evidence"],
            "owner": _owner_for_dimension(dimension["id"]),
        }
        for index, dimension in enumerate(
            [dimension for dimension in dimensions if dimension["status"] != "ready"],
            start=1,
        )
    ]
    if evaluation and evaluation.get("recommendation") in {"no", "strong_no"}:
        blockers.append(
            {
                "id": f"BLK{len(blockers) + 1}",
                "dimension_id": "launch_evidence",
                "severity": "critical",
                "description": f"Evaluation recommendation is {evaluation.get('recommendation')}.",
                "missing_evidence": ["evaluation.recommendation"],
                "owner": "product_owner",
            }
        )
    return blockers


def _required_signoffs(
    decision: str,
    dimensions: list[dict[str, Any]],
    project: dict[str, Any],
) -> list[dict[str, Any]]:
    blocked = {dimension["id"] for dimension in dimensions if dimension["status"] != "ready"}
    return [
        _signoff("SO1", "product_owner", "Scope, value, and launch evidence are acceptable.", blocked, {"scope", "launch_evidence"}),
        _signoff("SO2", "technical_owner", "Implementation, validation, and rollback path are ready.", blocked, {"implementation", "rollback"}),
        _signoff("SO3", "security_owner", "Security review has no unresolved release blockers.", blocked, {"security"}),
        _signoff("SO4", "operations_owner", "Observability and operational response are ready.", blocked, {"observability", "rollback"}),
        _signoff("SO5", "support_owner", "Support handoff and escalation path are ready.", blocked, {"support"}),
        {
            "id": "SO6",
            "role": "launch_owner",
            "status": "pending" if decision == "go" else "blocked",
            "requirement": "Final go/no-go decision is recorded with all required owner signoffs.",
            "owner_hint": _compact(project.get("buyer")) or "launch sponsor",
            "blocked_by_dimensions": sorted(blocked),
        },
    ]


def _signoff(
    id_: str,
    role: str,
    requirement: str,
    blocked: set[str],
    dimensions: set[str],
) -> dict[str, Any]:
    blocked_by = sorted(blocked & dimensions)
    return {
        "id": id_,
        "role": role,
        "status": "blocked" if blocked_by else "pending",
        "requirement": requirement,
        "owner_hint": role,
        "blocked_by_dimensions": blocked_by,
    }


def _owner_for_dimension(dimension_id: str) -> str:
    return {
        "scope": "product_owner",
        "implementation": "technical_owner",
        "security": "security_owner",
        "observability": "operations_owner",
        "rollback": "technical_owner",
        "support": "support_owner",
        "launch_evidence": "launch_owner",
    }.get(dimension_id, "launch_owner")


def _render_dimension(item: dict[str, Any]) -> list[str]:
    missing = item.get("missing_evidence") or []
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('label'))}",
        "",
        f"- Status: {_text(item.get('status'))}",
        f"- Required: {_text(item.get('required'))}",
        f"- Missing evidence: {', '.join(_text(value) for value in missing) if missing else 'none'}",
        f"- Remediation: {_text(item.get('remediation')) or 'none'}",
    ]


def _render_blocker(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('dimension_id'))}",
        "",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Missing evidence: {', '.join(_text(value) for value in item.get('missing_evidence') or []) or 'none'}",
    ]


def _render_signoff(item: dict[str, Any]) -> list[str]:
    blocked_by = item.get("blocked_by_dimensions") or []
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        "",
        f"- Status: {_text(item.get('status'))}",
        f"- Requirement: {_text(item.get('requirement'))}",
        f"- Owner hint: {_text(item.get('owner_hint'))}",
        f"- Blocked by: {', '.join(_text(value) for value in blocked_by) if blocked_by else 'none'}",
    ]


def _extend_section(
    lines: list[str],
    title: str,
    items: list[Any],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _csv_rows(gate: dict[str, Any]) -> list[dict[str, str]]:
    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    blockers = [item for item in gate.get("blockers") or [] if isinstance(item, dict)]
    rows = [
        _csv_row(
            gate,
            section="summary",
            type_="gate",
            item_id="gate",
            name=summary.get("title") or "Release readiness gate",
            status=summary.get("decision"),
            owner="launch_owner",
            evidence={
                "ready_dimension_count": summary.get("ready_dimension_count"),
                "blocker_count": summary.get("blocker_count"),
                "recommendation": summary.get("recommendation"),
                "overall_score": summary.get("overall_score"),
            },
            blocker_risk=_blocker_risk_for_gate(blockers),
            next_action=_next_action_for_gate(summary, blockers),
        )
    ]
    for dimension in gate.get("readiness_dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        rows.append(
            _csv_row(
                gate,
                section="readiness",
                type_="check",
                item_id=dimension.get("id"),
                dimension_id=dimension.get("id"),
                name=dimension.get("label"),
                status=dimension.get("status"),
                required=dimension.get("required"),
                owner=_owner_for_dimension(_text(dimension.get("id"))),
                evidence=dimension.get("evidence"),
                blocker_risk=_blocker_risk_for_dimension(dimension, blockers),
                next_action=dimension.get("remediation") if dimension.get("status") != "ready" else "",
            )
        )
    return rows


def _csv_row(
    gate: dict[str, Any],
    *,
    section: str,
    type_: str,
    item_id: Any = None,
    dimension_id: Any = None,
    name: Any = None,
    status: Any = None,
    required: Any = None,
    owner: Any = None,
    evidence: Any = None,
    blocker_risk: Any = None,
    next_action: Any = None,
) -> dict[str, str]:
    source = gate.get("source") if isinstance(gate.get("source"), dict) else {}
    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "source_system": source.get("system"),
        "source_type": source.get("type"),
        "source_idea_id": source.get("idea_id"),
        "source_status": source.get("status"),
        "source_domain": source.get("domain"),
        "source_category": source.get("category"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "title": summary.get("title"),
        "decision": summary.get("decision"),
        "go": summary.get("go"),
        "workflow_context": summary.get("workflow_context"),
        "target_user": summary.get("target_user"),
        "buyer": summary.get("buyer"),
        "recommendation": summary.get("recommendation"),
        "overall_score": summary.get("overall_score"),
        "item_id": item_id,
        "dimension_id": dimension_id,
        "name": name,
        "status": status,
        "required": required,
        "owner": owner,
        "evidence": evidence,
        "blocker_risk": blocker_risk,
        "next_action": next_action,
    }
    return {column: _csv_value(values.get(column)) for column in RELEASE_READINESS_GATE_CSV_COLUMNS}


def _blocker_risk_for_gate(blockers: list[dict[str, Any]]) -> str:
    if not blockers:
        return ""
    return "; ".join(
        _csv_value(
            {
                "id": blocker.get("id"),
                "dimension": blocker.get("dimension_id"),
                "severity": blocker.get("severity"),
                "description": blocker.get("description"),
            }
        )
        for blocker in blockers
    )


def _blocker_risk_for_dimension(
    dimension: dict[str, Any], blockers: list[dict[str, Any]]
) -> str:
    dimension_id = dimension.get("id")
    matching_blockers = [
        blocker for blocker in blockers if blocker.get("dimension_id") == dimension_id
    ]
    if matching_blockers:
        return "; ".join(
            _csv_value(
                {
                    "id": blocker.get("id"),
                    "severity": blocker.get("severity"),
                    "missing_evidence": blocker.get("missing_evidence"),
                    "description": blocker.get("description"),
                }
            )
            for blocker in matching_blockers
        )
    missing = dimension.get("missing_evidence") or []
    if missing:
        return _csv_value({"missing_evidence": missing})
    return ""


def _next_action_for_gate(summary: dict[str, Any], blockers: list[dict[str, Any]]) -> str:
    if blockers:
        return "Resolve release blockers before recording the final go/no-go decision."
    if summary.get("decision") == "go":
        return "Record final go/no-go decision with all required owner signoffs."
    return ""


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_compact(key)}={_csv_value(item)}"
            for key, item in sorted(value.items())
            if _csv_value(item)
        )
    if isinstance(value, list):
        return "; ".join(_csv_value(item) for item in value if _csv_value(item))
    return str(value).strip()


def _evidence(items: list[tuple[str, Any]]) -> dict[str, Any]:
    return {key: _evidence_value(value) for key, value in items if _has_value(value)}


def _evidence_value(value: Any) -> Any:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, bool):
        return value
    return _compact(value)


def _missing(evidence: dict[str, Any], keys: list[str]) -> list[str]:
    return [key for key in keys if key not in evidence]


def _acceptance_criteria(spec: dict[str, Any]) -> list[Any]:
    criteria = spec.get("acceptance_criteria")
    if not isinstance(criteria, dict):
        return []
    items: list[Any] = []
    for key in ("functional_criteria", "non_functional_criteria"):
        items.extend(_list(criteria.get(key)))
    return items


def _evidence_references(spec: dict[str, Any]) -> list[str]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs: list[str] = []
    for key in ("insight_ids", "signal_ids", "source_idea_ids"):
        refs.extend(_compact(item) for item in _list(evidence.get(key)) if _compact(item))
    if _compact(evidence.get("rationale")):
        refs.append("evidence.rationale")
    return sorted(set(refs))


def _workflow(project: dict[str, Any]) -> str:
    return _compact(project.get("workflow_context")) or "primary workflow"


def _stack_label(stack: Any) -> str:
    if not isinstance(stack, dict):
        return ""
    values = [f"{key}={value}" for key, value in sorted(stack.items()) if _compact(value)]
    return ", ".join(values)


def _haystack(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_haystack(item)}" for key, item in sorted(value.items()))
    if isinstance(value, list):
        return " ".join(_haystack(item) for item in value)
    return _compact(value).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _has_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return bool(value)
    return bool(_compact(value))


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
