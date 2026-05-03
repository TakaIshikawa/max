"""Deterministic technical-feasibility reports for persisted design briefs."""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "max.design_brief.technical_feasibility.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "dimension",
    "title",
    "name",
    "category",
    "type",
    "constraint",
    "dependency",
    "risk",
    "risk_level",
    "confidence",
    "owner",
    "recommendation",
    "next_action",
    "owner_or_type",
    "rationale",
    "validation_step",
    "detail",
    "details",
)

_INTEGRATION_KEYWORDS = {
    "api": "external_api",
    "apis": "external_api",
    "adapter": "adapter",
    "adapters": "adapter",
    "browser": "browser",
    "ci": "ci",
    "cli": "cli",
    "github": "developer_platform",
    "jira": "work_management",
    "linear": "work_management",
    "notion": "workspace_tool",
    "slack": "messaging",
    "webhook": "webhook",
}

_DATA_KEYWORDS = (
    "customer",
    "dataset",
    "data",
    "events",
    "feedback",
    "metrics",
    "pii",
    "signals",
    "telemetry",
    "workflow",
)

_HIGH_RISK_KEYWORDS = (
    "compliance",
    "credential",
    "external",
    "hipaa",
    "legal",
    "oauth",
    "pii",
    "privacy",
    "regulated",
    "security",
)


def build_design_brief_technical_feasibility(design_brief: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-ready pre-build feasibility report from a design brief payload."""
    source_ids = list(design_brief.get("source_idea_ids") or [])
    architecture_assumptions = _architecture_assumptions(design_brief)
    integration_surface = _integration_surface(design_brief)
    data_dependencies = _data_dependencies(design_brief)
    unknowns = _unknowns(design_brief, integration_surface, data_dependencies)
    build_complexity = _build_complexity(
        design_brief,
        integration_surface=integration_surface,
        data_dependencies=data_dependencies,
        unknowns=unknowns,
    )
    feasibility_verdict = _feasibility_verdict(build_complexity, unknowns)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_ids,
        },
        "feasibility_verdict": feasibility_verdict,
        "architecture_assumptions": architecture_assumptions,
        "integration_surface": integration_surface,
        "data_dependencies": data_dependencies,
        "build_complexity": build_complexity,
        "unknowns": unknowns,
        "recommended_spike_plan": _recommended_spike_plan(
            feasibility_verdict,
            integration_surface=integration_surface,
            data_dependencies=data_dependencies,
            unknowns=unknowns,
        ),
    }


def render_design_brief_technical_feasibility(report: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Render a technical-feasibility report as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported technical feasibility format: {fmt}")

    brief = report["design_brief"]
    verdict = report["feasibility_verdict"]
    complexity = report["build_complexity"]
    lines = [
        f"# Technical Feasibility: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
        "## Feasibility Verdict",
        "",
        f"- **Verdict**: `{verdict['verdict']}`",
        f"- **Risk level**: `{verdict['risk_level']}`",
        f"- **Next decision**: {verdict['next_decision']}",
        "",
        verdict["rationale"],
        "",
        "## Architecture Assumptions",
        "",
    ]
    for item in report["architecture_assumptions"]:
        lines.extend(
            [
                f"- **{item['id']}**: {item['assumption']}",
                f"  Rationale: {item['rationale']} Confidence: `{item['confidence']}`.",
            ]
        )

    lines.extend(["", "## Integration Surface", ""])
    for item in report["integration_surface"]:
        lines.extend(
            [
                f"- **{item['name']}** (`{item['type']}`, risk `{item['risk_level']}`): {item['rationale']}",
                f"  Validation: {item['validation_step']}",
            ]
        )

    lines.extend(["", "## Data Dependencies", ""])
    for item in report["data_dependencies"]:
        lines.extend(
            [
                f"- **{item['name']}** (`{item['criticality']}`, risk `{item['risk_level']}`): {item['rationale']}",
                f"  Validation: {item['validation_step']}",
            ]
        )

    lines.extend(
        [
            "",
            "## Build Complexity",
            "",
            f"- **Level**: `{complexity['level']}`",
            f"- **Score**: {complexity['score']}/10",
            f"- **Estimated MVP effort**: {complexity['estimated_mvp_effort']}",
            "",
            "### Complexity Drivers",
            "",
        ]
    )
    lines.extend(f"- {driver}" for driver in complexity["drivers"])
    lines.extend(["", "## Unknowns", ""])
    lines.extend(
        f"- **{item['id']}**: {item['unknown']} Impact: {item['impact']} Resolution: {item['resolution_path']}"
        for item in report["unknowns"]
    )
    lines.extend(["", "## Recommended Spike Plan", ""])
    for item in report["recommended_spike_plan"]:
        lines.extend(
            [
                f"### {item['id']}: {item['title']}",
                "",
                f"- **Duration**: {item['duration']}",
                f"- **Goal**: {item['goal']}",
                f"- **Exit criteria**: {item['exit_criteria']}",
                "",
            ]
        )
        lines.extend(f"- {step}" for step in item["steps"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_design_brief_technical_feasibility(
    path: Path,
    report: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_design_brief_technical_feasibility(report, fmt=fmt), encoding="utf-8")


def technical_feasibility_filename(design_brief: dict[str, Any], *, fmt: str) -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return f"{_filename_part(str(design_brief['id']))}-technical-feasibility.{extension}"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    brief = report["design_brief"]
    base = {
        "design_brief_id": str(brief["id"]),
        "design_brief_title": str(brief["title"]),
    }
    rows: list[dict[str, str]] = []

    verdict = report.get("feasibility_verdict", {})
    rows.append(
        _csv_row(
            base,
            section="feasibility_verdict",
            item_id="V1",
            dimension="technical_feasibility",
            title="Feasibility verdict",
            name=verdict.get("verdict", ""),
            category="decision",
            type=verdict.get("verdict", ""),
            risk=verdict.get("blocking_risks", []),
            risk_level=verdict.get("risk_level", ""),
            recommendation=verdict.get("next_decision", ""),
            rationale=verdict.get("rationale", ""),
            next_action=verdict.get("next_decision", ""),
            validation_step=verdict.get("next_decision", ""),
            detail={"blocking_risks": verdict.get("blocking_risks", [])},
        )
    )

    for item in report.get("architecture_assumptions", []):
        rows.append(
            _csv_row(
                base,
                section="architecture_assumptions",
                item_id=item.get("id", ""),
                dimension="architecture",
                title=item.get("assumption", ""),
                name=item.get("assumption", ""),
                category="architecture_assumption",
                type="assumption",
                owner=item.get("owner", ""),
                confidence=item.get("confidence", ""),
                rationale=item.get("rationale", ""),
                detail={"source_fields": item.get("source_fields", [])},
            )
        )

    for item in report.get("integration_surface", []):
        rows.append(
            _csv_row(
                base,
                section="integration_surface",
                item_id=item.get("id", ""),
                dimension="integration_surface",
                title=item.get("name", ""),
                name=item.get("name", ""),
                category="integration",
                type=item.get("type", ""),
                dependency=item.get("name", ""),
                risk=item.get("risk_level", ""),
                risk_level=item.get("risk_level", ""),
                owner=item.get("owner", ""),
                owner_or_type=item.get("type", ""),
                rationale=item.get("rationale", ""),
                next_action=item.get("validation_step", ""),
                validation_step=item.get("validation_step", ""),
            )
        )

    for item in report.get("data_dependencies", []):
        rows.append(
            _csv_row(
                base,
                section="data_dependencies",
                item_id=item.get("id", ""),
                dimension="data_dependency",
                title=item.get("name", ""),
                name=item.get("name", ""),
                category="data_dependency",
                type=item.get("criticality", ""),
                dependency=item.get("source", ""),
                risk=item.get("risk_level", ""),
                risk_level=item.get("risk_level", ""),
                owner=item.get("owner", ""),
                owner_or_type=item.get("criticality", ""),
                rationale=item.get("rationale", ""),
                next_action=item.get("validation_step", ""),
                validation_step=item.get("validation_step", ""),
                detail={"source": item.get("source", "")},
            )
        )

    complexity = report.get("build_complexity", {})
    rows.append(
        _csv_row(
            base,
            section="build_complexity",
            item_id="C1",
            dimension="build_complexity",
            title="Build complexity",
            name=complexity.get("level", ""),
            category="complexity",
            type=complexity.get("estimated_mvp_effort", ""),
            constraint=complexity.get("constraints", []),
            risk=complexity.get("level", ""),
            risk_level=complexity.get("level", ""),
            owner_or_type=complexity.get("estimated_mvp_effort", ""),
            rationale="; ".join(str(driver) for driver in complexity.get("drivers", [])),
            detail={
                "constraints": complexity.get("constraints", []),
                "drivers": complexity.get("drivers", []),
                "estimated_mvp_effort": complexity.get("estimated_mvp_effort", ""),
                "score": complexity.get("score", ""),
            },
        )
    )

    for item in report.get("unknowns", []):
        rows.append(
            _csv_row(
                base,
                section="unknowns",
                item_id=item.get("id", ""),
                dimension="unknown",
                title=item.get("unknown", ""),
                name=item.get("unknown", ""),
                category="unknown",
                type=item.get("impact", ""),
                risk=item.get("impact", ""),
                rationale=item.get("impact", ""),
                next_action=item.get("resolution_path", ""),
                validation_step=item.get("resolution_path", ""),
            )
        )

    for item in report.get("recommended_spike_plan", []):
        rows.append(
            _csv_row(
                base,
                section="recommended_spike_plan",
                item_id=item.get("id", ""),
                dimension="validation_action",
                title=item.get("title", ""),
                name=item.get("title", ""),
                category="spike",
                type=item.get("duration", ""),
                owner=item.get("owner", ""),
                recommendation=item.get("exit_criteria", ""),
                owner_or_type=item.get("duration", ""),
                rationale=item.get("goal", ""),
                next_action=item.get("exit_criteria", ""),
                validation_step=item.get("exit_criteria", ""),
                detail={"steps": item.get("steps", [])},
            )
        )

    return rows


def _csv_row(base: dict[str, str], **values: Any) -> dict[str, str]:
    row: dict[str, Any] = {**base, **values}
    detail = _csv_detail(row.get("detail"))
    if detail:
        row["detail"] = detail
        row.setdefault("details", detail)
    return {column: _csv_cell(row.get(column)) for column in CSV_COLUMNS}


def _csv_detail(value: Any) -> str:
    if value in (None, ""):
        return ""
    return _compact_json(value)


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        values = sorted(value, key=str) if isinstance(value, set) else value
        return "; ".join(_csv_cell(item) for item in values if _csv_cell(item))
    if isinstance(value, dict):
        return _compact_json(value)
    return str(value)


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _architecture_assumptions(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    concept = _clean(design_brief.get("merged_product_concept")) or design_brief["title"]
    workflow = _clean(design_brief.get("workflow_context")) or "the target workflow"
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))

    assumptions = [
        {
            "id": "A1",
            "assumption": "The MVP can be delivered as a focused workflow service with a narrow user-facing surface.",
            "rationale": f"The concept centers on {concept}.",
            "confidence": "medium" if concept else "low",
            "source_fields": ["merged_product_concept"],
        },
        {
            "id": "A2",
            "assumption": "The first implementation should optimize for the persisted workflow before broad platform coverage.",
            "rationale": f"The brief identifies the workflow as {workflow}.",
            "confidence": "high" if _clean(design_brief.get("workflow_context")) else "low",
            "source_fields": ["workflow_context"],
        },
        {
            "id": "A3",
            "assumption": "Initial scope can be sequenced into testable milestones without committing to a large architecture upfront.",
            "rationale": _scope_rationale(scope, milestones),
            "confidence": "high" if scope and milestones else "medium" if scope or milestones else "low",
            "source_fields": ["mvp_scope", "first_milestones"],
        },
    ]
    return assumptions


def _integration_surface(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    text = _brief_text(design_brief)
    found: dict[str, str] = {}
    for keyword, surface_type in _INTEGRATION_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text, flags=re.IGNORECASE):
            found[surface_type] = keyword

    surfaces = [
        _surface(
            "I1",
            "Primary product interface",
            "application_surface",
            "medium",
            "The brief requires a user-facing path through the MVP workflow.",
            "Prototype the core happy path with mocked persistence and one representative user task.",
        )
    ]
    for index, (surface_type, keyword) in enumerate(sorted(found.items()), start=2):
        risk_level = "high" if surface_type in {"external_api", "developer_platform", "work_management"} else "medium"
        surfaces.append(
            _surface(
                f"I{index}",
                _titleize(surface_type),
                surface_type,
                risk_level,
                f"The brief references {keyword}, which implies an integration boundary to validate.",
                "Verify authentication, rate limits, sandbox availability, and failure handling before build planning.",
            )
        )
    return surfaces


def _data_dependencies(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    text = _brief_text(design_brief)
    dependencies = [
        {
            "id": "D1",
            "name": "Persisted design brief payload",
            "source": "max.store.design_briefs",
            "criticality": "required",
            "risk_level": "low",
            "rationale": "The report and downstream implementation handoff depend on fields already persisted with the brief.",
            "validation_step": "Confirm required brief fields are present in export fixtures and CLI output.",
        }
    ]
    matched = [keyword for keyword in _DATA_KEYWORDS if re.search(rf"\b{keyword}\b", text, flags=re.IGNORECASE)]
    if matched:
        risk = "high" if {"pii", "customer"} & set(matched) else "medium"
        dependencies.append(
            {
                "id": "D2",
                "name": "Workflow and validation data",
                "source": "customer discovery, product telemetry, or source signals",
                "criticality": "required",
                "risk_level": risk,
                "rationale": f"The brief references data-bearing terms: {', '.join(sorted(set(matched)))}.",
                "validation_step": "Inventory source, owner, retention, privacy constraints, and minimum viable sample size.",
            }
        )
    return dependencies


def _build_complexity(
    design_brief: dict[str, Any],
    *,
    integration_surface: list[dict[str, Any]],
    data_dependencies: list[dict[str, Any]],
    unknowns: list[dict[str, Any]],
) -> dict[str, Any]:
    scope_count = len(_string_list(design_brief.get("mvp_scope")))
    milestone_count = len(_string_list(design_brief.get("first_milestones")))
    high_risk_count = sum(
        1
        for item in [*integration_surface, *data_dependencies]
        if item["risk_level"] == "high"
    )
    score = 2 + min(scope_count, 3) + min(milestone_count, 2) + high_risk_count + min(len(unknowns), 2)
    score = min(score, 10)
    level = "low" if score <= 4 else "medium" if score <= 7 else "high"
    drivers = [
        f"{scope_count or 1} MVP scope item(s) need implementation sequencing.",
        f"{len(integration_surface)} integration surface(s) require validation.",
        f"{len(data_dependencies)} data dependency group(s) need ownership and quality checks.",
    ]
    if unknowns:
        drivers.append(f"{len(unknowns)} unresolved unknown(s) should be closed before autonomous build.")
    if _has_high_risk_text(design_brief):
        drivers.append("Brief risk text includes security, privacy, compliance, or external dependency concerns.")

    return {
        "level": level,
        "score": score,
        "estimated_mvp_effort": "1-2 weeks" if level == "low" else "2-4 weeks" if level == "medium" else "4+ weeks",
        "drivers": drivers,
        "constraints": _constraints(design_brief),
    }


def _unknowns(
    design_brief: dict[str, Any],
    integration_surface: list[dict[str, Any]],
    data_dependencies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unknowns: list[dict[str, Any]] = []
    if not _clean(design_brief.get("workflow_context")):
        unknowns.append(_unknown("U1", "Target workflow boundaries are not explicit.", "Architecture may optimize for the wrong handoff.", "Map the workflow steps and entry points with one target user."))
    if not _string_list(design_brief.get("mvp_scope")):
        unknowns.append(_unknown("U2", "MVP scope is not decomposed.", "Build agents may overbuild or choose inconsistent boundaries.", "Convert the product concept into 3-5 implementation slices."))
    if not _clean(design_brief.get("validation_plan")):
        unknowns.append(_unknown("U3", "Validation plan is missing.", "There is no pre-build success or stop criterion.", "Define a smoke test or technical proof threshold before implementation."))
    if any(item["risk_level"] == "high" for item in integration_surface):
        unknowns.append(_unknown("U4", "External integration constraints are unresolved.", "Authentication, rate limits, or API churn could block the MVP.", "Run an integration spike against sandbox or mocked provider contracts."))
    if any(item["risk_level"] == "high" for item in data_dependencies):
        unknowns.append(_unknown("U5", "Sensitive or customer data handling is unresolved.", "Privacy or compliance work could change architecture requirements.", "Document data classification, consent, retention, and redaction requirements."))
    if not unknowns:
        unknowns.append(_unknown("U1", "Operational ownership after the first MVP is not proven.", "Support and monitoring expectations may be deferred until too late.", "Add a lightweight runbook and owner checklist during the spike."))
    return unknowns


def _feasibility_verdict(
    build_complexity: dict[str, Any],
    unknowns: list[dict[str, Any]],
) -> dict[str, Any]:
    risk_level = build_complexity["level"]
    if risk_level == "high":
        verdict = "spike_required"
        next_decision = "Complete the recommended spike plan before autonomous implementation."
    elif len(unknowns) >= 3:
        verdict = "conditionally_feasible"
        risk_level = "medium"
        next_decision = "Resolve the highest-impact unknowns, then proceed with a constrained MVP."
    else:
        verdict = "feasible_with_spikes"
        next_decision = "Proceed after a short integration and data validation spike."

    return {
        "verdict": verdict,
        "risk_level": risk_level,
        "rationale": (
            f"Build complexity is {build_complexity['level']} with "
            f"{len(unknowns)} unresolved unknown(s)."
        ),
        "blocking_risks": [item["unknown"] for item in unknowns if item["id"] != "U1" or len(unknowns) > 1],
        "next_decision": next_decision,
    }


def _recommended_spike_plan(
    verdict: dict[str, Any],
    *,
    integration_surface: list[dict[str, Any]],
    data_dependencies: list[dict[str, Any]],
    unknowns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    high_integration = [item for item in integration_surface if item["risk_level"] == "high"]
    high_data = [item for item in data_dependencies if item["risk_level"] in {"medium", "high"}]
    plan = [
        {
            "id": "S1",
            "title": "Architecture boundary spike",
            "duration": "0.5-1 day",
            "goal": "Confirm the smallest buildable service and interface boundary.",
            "steps": [
                "Sketch the core workflow sequence and required state transitions.",
                "Identify owned code, external systems, and manual fallback paths.",
                "Define the first demonstrable happy path for the MVP.",
            ],
            "exit_criteria": "One implementation slice has clear inputs, outputs, owner, and rollback path.",
        },
        {
            "id": "S2",
            "title": "Integration contract spike",
            "duration": "1-2 days" if high_integration else "0.5 day",
            "goal": "Validate the riskiest integration contracts before implementation starts.",
            "steps": [
                "List credentials, sandbox setup, rate limits, and provider failure modes.",
                "Build or mock one request-response path for each high-risk integration.",
                "Capture retry, timeout, and degraded-mode behavior.",
            ],
            "exit_criteria": "No required integration remains without an auth path, contract fixture, or mock strategy.",
        },
        {
            "id": "S3",
            "title": "Data readiness spike",
            "duration": "1 day" if high_data else "0.5 day",
            "goal": "Confirm data availability, quality, ownership, and handling constraints.",
            "steps": [
                "Inventory required records, sample volume, freshness, and retention needs.",
                "Classify sensitive data and document redaction requirements.",
                "Create a minimal fixture set for autonomous build and tests.",
            ],
            "exit_criteria": "Build agents have deterministic fixtures and explicit data handling constraints.",
        },
    ]
    if verdict["risk_level"] == "high" or len(unknowns) >= 3:
        plan.append(
            {
                "id": "S4",
                "title": "Build/no-build review",
                "duration": "0.5 day",
                "goal": "Turn unresolved unknowns into an implementation decision.",
                "steps": [
                    "Review spike findings against the feasibility verdict.",
                    "Promote remaining blockers into implementation requirements or stop criteria.",
                    "Update MVP scope before assigning autonomous build work.",
                ],
                "exit_criteria": "Decision is recorded as proceed, revise, or stop with named blockers.",
            }
        )
    return plan


def _surface(
    item_id: str,
    name: str,
    surface_type: str,
    risk_level: str,
    rationale: str,
    validation_step: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "type": surface_type,
        "risk_level": risk_level,
        "rationale": rationale,
        "validation_step": validation_step,
    }


def _unknown(item_id: str, unknown: str, impact: str, resolution_path: str) -> dict[str, str]:
    return {
        "id": item_id,
        "unknown": unknown,
        "impact": impact,
        "resolution_path": resolution_path,
    }


def _constraints(design_brief: dict[str, Any]) -> list[str]:
    constraints = []
    if _clean(design_brief.get("buyer")):
        constraints.append(f"Buyer path must satisfy {design_brief['buyer']}.")
    if _clean(design_brief.get("specific_user")):
        constraints.append(f"Primary UX must fit {design_brief['specific_user']}.")
    for risk in _string_list(design_brief.get("risks"))[:3]:
        constraints.append(f"Risk to manage: {risk}")
    return constraints or ["No explicit technical constraints were captured in the brief."]


def _scope_rationale(scope: list[str], milestones: list[str]) -> str:
    if scope and milestones:
        return f"Scope includes {', '.join(scope[:2])}; first milestones include {', '.join(milestones[:2])}."
    if scope:
        return f"Scope includes {', '.join(scope[:3])}."
    if milestones:
        return f"First milestones include {', '.join(milestones[:3])}."
    return "The brief does not yet provide detailed MVP scope or milestones."


def _brief_text(design_brief: dict[str, Any]) -> str:
    values = [
        design_brief.get("title"),
        design_brief.get("domain"),
        design_brief.get("theme"),
        design_brief.get("buyer"),
        design_brief.get("specific_user"),
        design_brief.get("workflow_context"),
        design_brief.get("why_this_now"),
        design_brief.get("merged_product_concept"),
        design_brief.get("synthesis_rationale"),
        design_brief.get("validation_plan"),
        *_string_list(design_brief.get("mvp_scope")),
        *_string_list(design_brief.get("first_milestones")),
        *_string_list(design_brief.get("risks")),
    ]
    return " ".join(_clean(value) for value in values if _clean(value))


def _has_high_risk_text(design_brief: dict[str, Any]) -> bool:
    text = _brief_text(design_brief).lower()
    return any(keyword in text for keyword in _HIGH_RISK_KEYWORDS)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, tuple):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _titleize(value: str) -> str:
    return value.replace("_", " ").title()


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
