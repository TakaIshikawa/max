"""Consolidated design-brief handoff bundle exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from max.analysis.blueprint_export import build_blueprint_source_brief
from max.analysis.design_brief_competitive_landscape import (
    build_design_brief_competitive_landscape,
    render_design_brief_competitive_landscape,
)
from max.analysis.design_brief_evidence_matrix import (
    build_design_brief_evidence_matrix,
    render_design_brief_evidence_matrix,
)
from max.analysis.design_brief_prd import build_design_brief_prd, render_design_brief_prd
from max.analysis.design_brief_pricing_strategy import (
    build_design_brief_pricing_strategy,
    render_design_brief_pricing_strategy,
)
from max.analysis.design_brief_roadmap import build_design_brief_roadmap, render_design_brief_roadmap
from max.analysis.design_brief_risk_register import (
    build_design_brief_risk_register,
    render_design_brief_risk_register,
)
from max.analysis.design_validation import build_validation_plan, render_validation_plan
from max.analysis.market_sizing import build_market_sizing_report, render_market_sizing_report
from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.bundle.v1"

ARTIFACT_NAMES: tuple[str, ...] = (
    "design_brief",
    "blueprint_source_brief",
    "validation_plan",
    "evidence_matrix",
    "risk_register",
    "roadmap",
    "prd",
    "pricing_strategy",
    "market_sizing",
    "competitive_landscape",
)

ArtifactBuilder = Callable[[Store, dict[str, Any], str], dict[str, Any] | None]


def build_design_brief_bundle(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a single payload containing a design brief and derived handoff artifacts."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": brief_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "artifact_status": {},
    }
    _record_generated(bundle, "design_brief", design_brief)

    builders: tuple[tuple[str, ArtifactBuilder], ...] = (
        ("blueprint_source_brief", _build_blueprint),
        ("validation_plan", _build_validation_plan),
        ("evidence_matrix", _build_evidence_matrix),
        ("risk_register", _build_risk_register),
        ("roadmap", _build_roadmap),
        ("prd", _build_prd),
        ("pricing_strategy", _build_pricing_strategy),
        ("market_sizing", _build_market_sizing),
        ("competitive_landscape", _build_competitive_landscape),
    )
    for name, builder in builders:
        try:
            artifact = builder(store, design_brief, brief_id)
        except Exception as exc:  # pragma: no cover - exercised with monkeypatch in tests.
            bundle[name] = None
            bundle["artifact_status"][name] = {
                "status": "errored",
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue

        if artifact is None:
            bundle[name] = None
            bundle["artifact_status"][name] = {"status": "missing"}
        else:
            _record_generated(bundle, name, artifact)

    return bundle


def render_design_brief_bundle(bundle: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a design-brief bundle as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(bundle, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported design brief bundle format: {fmt}")

    brief = bundle["design_brief"]
    lines = [
        f"# Design Brief Bundle: {brief['title']}",
        "",
        f"Schema: `{bundle['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
        "## Artifact Status",
        "",
    ]
    for name in ARTIFACT_NAMES:
        status = bundle.get("artifact_status", {}).get(name, {"status": "missing"})
        label = _title(name)
        line = f"- **{label}**: `{status['status']}`"
        if status.get("error"):
            line += f" - {status['error']}"
        lines.append(line)

    lines.extend(["", "## Design Brief", ""])
    lines.extend(
        [
            f"- **Buyer**: {brief.get('buyer') or 'TBD'}",
            f"- **User**: {brief.get('specific_user') or 'TBD'}",
            f"- **Workflow**: {brief.get('workflow_context') or 'TBD'}",
            f"- **Why now**: {brief.get('why_this_now') or 'TBD'}",
            "",
            "### MVP Scope",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _string_list(brief.get("mvp_scope")) or ["TBD"])
    lines.extend(["", "### First Milestones", ""])
    lines.extend(f"- {item}" for item in _string_list(brief.get("first_milestones")) or ["TBD"])
    lines.extend(["", "### Risks", ""])
    lines.extend(f"- {item}" for item in _string_list(brief.get("risks")) or ["TBD"])
    lines.append("")

    _append_artifact_section(
        lines,
        "Blueprint Source Brief",
        bundle.get("blueprint_source_brief"),
        _render_blueprint_markdown,
    )
    _append_artifact_section(lines, "Validation Plan", bundle.get("validation_plan"), _render_validation)
    _append_artifact_section(lines, "Evidence Matrix", bundle.get("evidence_matrix"), _render_evidence)
    _append_artifact_section(lines, "Risk Register", bundle.get("risk_register"), _render_risk)
    _append_artifact_section(lines, "Roadmap", bundle.get("roadmap"), _render_roadmap)
    _append_artifact_section(lines, "PRD", bundle.get("prd"), _render_prd)
    _append_artifact_section(lines, "Pricing Strategy", bundle.get("pricing_strategy"), _render_pricing)
    _append_artifact_section(lines, "Market Sizing", bundle.get("market_sizing"), _render_market)
    _append_artifact_section(
        lines,
        "Competitive Landscape",
        bundle.get("competitive_landscape"),
        _render_competitive,
    )

    return "\n".join(lines).rstrip() + "\n"


def _record_generated(bundle: dict[str, Any], name: str, artifact: dict[str, Any]) -> None:
    bundle[name] = artifact
    bundle["artifact_status"][name] = {"status": "generated"}


def _build_blueprint(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_blueprint_source_brief(store, design_brief)


def _build_validation_plan(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_validation_plan(store, design_brief)


def _build_evidence_matrix(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_design_brief_evidence_matrix(store, design_brief)


def _build_risk_register(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_design_brief_risk_register(store, brief_id)


def _build_roadmap(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_design_brief_roadmap(store, brief_id)


def _build_prd(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_design_brief_prd(store, brief_id)


def _build_pricing_strategy(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_design_brief_pricing_strategy(store, brief_id)


def _build_market_sizing(store: Store, design_brief: dict[str, Any], brief_id: str) -> dict[str, Any] | None:
    return build_market_sizing_report(store, design_brief)


def _build_competitive_landscape(
    store: Store,
    design_brief: dict[str, Any],
    brief_id: str,
) -> dict[str, Any] | None:
    return build_design_brief_competitive_landscape(store, brief_id)


def _append_artifact_section(
    lines: list[str],
    heading: str,
    artifact: dict[str, Any] | None,
    renderer: Callable[[dict[str, Any]], str],
) -> None:
    lines.extend([f"## {heading}", ""])
    if artifact is None:
        lines.extend(["Artifact unavailable. See artifact status above.", ""])
        return
    rendered = renderer(artifact).strip()
    lines.extend(_demote_headings(rendered).splitlines())
    lines.append("")


def _render_blueprint_markdown(packet: dict[str, Any]) -> str:
    brief = packet["design_brief"]
    lines = [
        f"### {brief['title']}",
        "",
        f"- **Blueprint schema**: `{packet['schema_version']}`",
        f"- **Recommended domain**: {packet['blueprint_import_hints']['recommended_domain']}",
        f"- **Source ideas**: {len(packet['source_ideas'])}",
        "",
    ]
    for idea in packet["source_ideas"]:
        label = idea.get("title") or "(missing source idea)"
        missing = " missing" if idea.get("missing") else ""
        lines.append(f"- `{idea['id']}` ({idea['role']}{missing}) - {label}")
    return "\n".join(lines) + "\n"


def _render_validation(plan: dict[str, Any]) -> str:
    return render_validation_plan(plan, fmt="markdown")


def _render_evidence(matrix: dict[str, Any]) -> str:
    return render_design_brief_evidence_matrix(matrix, fmt="markdown")


def _render_risk(register: dict[str, Any]) -> str:
    return render_design_brief_risk_register(register, fmt="markdown")


def _render_roadmap(roadmap: dict[str, Any]) -> str:
    return render_design_brief_roadmap(roadmap, fmt="markdown")


def _render_prd(prd: dict[str, Any]) -> str:
    return render_design_brief_prd(prd, fmt="markdown")


def _render_pricing(report: dict[str, Any]) -> str:
    return render_design_brief_pricing_strategy(report, fmt="markdown")


def _render_market(report: dict[str, Any]) -> str:
    return render_market_sizing_report(report, fmt="markdown")


def _render_competitive(report: dict[str, Any]) -> str:
    return render_design_brief_competitive_landscape(report, fmt="markdown")


def _demote_headings(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        if line.startswith("######"):
            lines.append(line)
        elif line.startswith("#"):
            lines.append("##" + line)
        else:
            lines.append(line)
    return "\n".join(lines)


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if str(value).strip():
        return [str(value)]
    return []
