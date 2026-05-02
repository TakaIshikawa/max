"""Deterministic assumption ledger export for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "max.design_brief.assumption_ledger.v1"

CSV_HEADERS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "group_id",
    "group_title",
    "assumption_id",
    "statement",
    "confidence_level",
    "confidence_score",
    "owner_hint",
    "validation_action",
    "evidence_links",
)

GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "desirability",
        "title": "Desirability",
        "owner_hint": "product discovery owner",
        "fallback": "Target users have an urgent enough problem to spend time validating this concept.",
        "fallback_fields": ["specific_user", "problem", "workflow_context"],
    },
    {
        "id": "feasibility",
        "title": "Feasibility",
        "owner_hint": "technical lead",
        "fallback": "The team can build and operate the MVP scope with acceptable technical risk.",
        "fallback_fields": ["mvp_scope", "tech_approach", "risks"],
    },
    {
        "id": "viability",
        "title": "Viability",
        "owner_hint": "business owner",
        "fallback": "The buyer will see enough measurable value to justify continued investment.",
        "fallback_fields": ["buyer", "value_proposition", "readiness_score"],
    },
    {
        "id": "go_to_market",
        "title": "Go-to-Market",
        "owner_hint": "go-to-market owner",
        "fallback": "The first customer segment is reachable and can be converted into qualified validation.",
        "fallback_fields": ["first_10_customers", "validation_plan", "domain"],
    },
)


def build_design_brief_assumption_ledger(design_brief: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-ready assumption ledger from a persisted design brief payload."""
    brief_id = _clean(design_brief.get("id")) or "unknown-design-brief"
    title = _clean(design_brief.get("title")) or "Untitled Design Brief"
    evidence_links = _evidence_links(design_brief)
    groups = [_assumption_group(config, design_brief, evidence_links) for config in GROUPS]
    unresolved = _unresolved_assumptions(design_brief, groups, evidence_links)
    actions = _next_validation_actions(groups, unresolved)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.assumption_ledger",
        "design_brief": {
            "id": brief_id,
            "title": title,
            "domain": _clean(design_brief.get("domain")),
            "theme": _clean(design_brief.get("theme")),
            "readiness_score": _number(design_brief.get("readiness_score")),
            "design_status": _clean(design_brief.get("design_status")),
            "lead_idea_id": _clean(design_brief.get("lead_idea_id")),
            "source_idea_ids": _string_list(design_brief.get("source_idea_ids")),
        },
        "summary": {
            "assumption_count": sum(len(group["assumptions"]) for group in groups),
            "unresolved_assumption_count": len(unresolved),
            "evidence_link_count": len(evidence_links),
            "low_confidence_count": sum(
                1
                for group in groups
                for assumption in group["assumptions"]
                if assumption["confidence_level"] == "low"
            ),
        },
        "assumption_groups": groups,
        "unresolved_assumptions": unresolved,
        "next_validation_actions": actions,
    }


def render_design_brief_assumption_ledger(
    ledger: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    """Render an assumption ledger as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(ledger)
    if fmt != "markdown":
        raise ValueError(f"Unsupported assumption ledger format: {fmt}")

    brief = ledger["design_brief"]
    lines = [
        f"# Assumption Ledger: {brief['title']}",
        "",
        f"Schema: `{ledger['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Readiness: {brief['readiness_score']:.1f}/100",
        "",
        "## Assumption Groups",
        "",
    ]
    for group in ledger["assumption_groups"]:
        lines.extend([f"### {group['title']}", ""])
        for assumption in group["assumptions"]:
            lines.extend(
                [
                    f"- **{assumption['statement']}**",
                    f"  Confidence: `{assumption['confidence_level']}` ({assumption['confidence_score']:.2f})",
                    f"  Owner hint: {assumption['owner_hint']}",
                    f"  Evidence links: {_inline_links(assumption['evidence_links'])}",
                    f"  Validation action: {assumption['validation_action']}",
                ]
            )
        lines.append("")

    lines.extend(["## Unresolved Assumptions", ""])
    if ledger["unresolved_assumptions"]:
        lines.extend(f"- {item}" for item in ledger["unresolved_assumptions"])
    else:
        lines.append("- None")

    lines.extend(["", "## Next Validation Actions", ""])
    lines.extend(
        f"- **{action['assumption_id']}** ({action['confidence_level']}): {action['action']}"
        for action in ledger["next_validation_actions"]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_design_brief_assumption_ledger(
    path: Path,
    ledger: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_design_brief_assumption_ledger(ledger, fmt=fmt), encoding="utf-8")


def assumption_ledger_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(_clean(design_brief.get("id")) or "design-brief")
    return f"{brief_id}-assumption-ledger.{extension}"


def _render_csv(ledger: dict[str, Any]) -> str:
    brief = ledger["design_brief"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\n")
    writer.writeheader()
    for group in ledger["assumption_groups"]:
        for assumption in group["assumptions"]:
            writer.writerow(
                {
                    "design_brief_id": brief["id"],
                    "design_brief_title": brief["title"],
                    "group_id": group["id"],
                    "group_title": group["title"],
                    "assumption_id": assumption["id"],
                    "statement": assumption["statement"],
                    "confidence_level": assumption["confidence_level"],
                    "confidence_score": f"{assumption['confidence_score']:.2f}",
                    "owner_hint": assumption["owner_hint"],
                    "validation_action": assumption["validation_action"],
                    "evidence_links": json.dumps(
                        assumption["evidence_links"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
    return output.getvalue()


def _assumption_group(
    config: dict[str, Any],
    design_brief: dict[str, Any],
    evidence_links: list[dict[str, Any]],
) -> dict[str, Any]:
    group_id = config["id"]
    assumptions = _specific_assumptions(group_id, design_brief, config["owner_hint"])
    if not assumptions:
        assumptions = [
            _assumption(
                group_id,
                1,
                config["fallback"],
                config["fallback_fields"],
                config["owner_hint"],
                design_brief,
                evidence_links,
                fallback=True,
            )
        ]
    return {
        "id": group_id,
        "title": config["title"],
        "assumptions": assumptions,
    }


def _specific_assumptions(
    group_id: str, design_brief: dict[str, Any], owner_hint: str
) -> list[dict[str, Any]]:
    specs: dict[str, list[tuple[str, list[str]]]] = {
        "desirability": [
            (
                f"{_user(design_brief)} has a recurring problem in {_workflow(design_brief)}.",
                ["specific_user", "problem", "workflow_context"],
            ),
            (
                f"The current workaround creates enough pain to motivate switching from {_workaround(design_brief)}.",
                ["current_workaround", "why_this_now"],
            ),
            (
                f"The proposed concept delivers a clear improvement: {_concept(design_brief)}.",
                ["merged_product_concept", "value_proposition"],
            ),
        ],
        "feasibility": [
            (
                "The MVP scope can be built as a coherent first release.",
                ["mvp_scope", "first_milestones"],
            ),
            (
                f"The technical approach is sufficient for implementation planning: {_tech_approach(design_brief)}.",
                ["tech_approach", "suggested_stack"],
            ),
            (
                "Known risks can be converted into mitigations before build expansion.",
                ["risks", "validation_plan"],
            ),
        ],
        "viability": [
            (
                f"{_buyer(design_brief)} has a strong enough reason to sponsor the workflow.",
                ["buyer", "value_proposition"],
            ),
            (
                "The brief has enough readiness and evidence to justify focused validation.",
                ["readiness_score", "evidence_counts", "source_idea_ids"],
            ),
            (
                "The validation plan can produce a clear continue, pivot, or stop decision.",
                ["validation_plan", "success_metric"],
            ),
        ],
        "go_to_market": [
            (
                f"The initial customer segment is reachable: {_first_customers(design_brief)}.",
                ["first_10_customers", "domain"],
            ),
            (
                "The domain and theme are specific enough for positioning and outbound targeting.",
                ["domain", "theme"],
            ),
            (
                "Validation work can recruit the buyer, user, and pilot stakeholders named in the brief.",
                ["buyer", "specific_user", "validation_plan"],
            ),
        ],
    }
    assumptions: list[dict[str, Any]] = []
    for index, (statement, fields) in enumerate(specs[group_id], start=1):
        if any(_has_value(design_brief.get(field)) for field in fields):
            assumptions.append(
                _assumption(
                    group_id,
                    index,
                    statement,
                    fields,
                    owner_hint,
                    design_brief,
                    _evidence_links(design_brief),
                    fallback=False,
                )
            )
    return assumptions


def _assumption(
    group_id: str,
    index: int,
    statement: str,
    source_fields: list[str],
    owner_hint: str,
    design_brief: dict[str, Any],
    evidence_links: list[dict[str, Any]],
    *,
    fallback: bool,
) -> dict[str, Any]:
    links = _links_for_fields(evidence_links, source_fields)
    confidence = _confidence(design_brief, source_fields, links, fallback=fallback)
    assumption_id = f"dba-{group_id}-{index:02d}"
    return {
        "id": assumption_id,
        "statement": _clean_sentence(statement),
        "group": group_id,
        "source_fields": source_fields,
        "evidence_links": links,
        "confidence_score": confidence["score"],
        "confidence_level": confidence["level"],
        "validation_action": _validation_action(group_id, source_fields, confidence["level"]),
        "owner_hint": owner_hint,
    }


def _confidence(
    design_brief: dict[str, Any],
    source_fields: list[str],
    evidence_links: list[dict[str, Any]],
    *,
    fallback: bool,
) -> dict[str, Any]:
    present = sum(1 for field in source_fields if _has_value(design_brief.get(field)))
    field_score = present / max(len(source_fields), 1)
    evidence_score = min(len(evidence_links) / 3.0, 1.0)
    readiness_score = min(max(_number(design_brief.get("readiness_score")) / 100.0, 0.0), 1.0)
    score = round(field_score * 0.55 + evidence_score * 0.25 + readiness_score * 0.20, 2)
    if fallback:
        score = min(score, 0.35)
    return {
        "score": score,
        "level": "high" if score >= 0.75 else "medium" if score >= 0.45 else "low",
    }


def _validation_action(group_id: str, source_fields: list[str], confidence_level: str) -> str:
    prefix = {
        "desirability": "Run problem interviews and capture quotes that confirm urgency, workaround pain, and switching intent.",
        "feasibility": "Run a technical spike or implementation review and record build constraints, risks, and acceptance criteria.",
        "viability": "Validate budget ownership, willingness to continue, and the measurable business outcome.",
        "go_to_market": "Test outreach against the first customer segment and record conversion, objections, and reachable channels.",
    }[group_id]
    if confidence_level == "low":
        missing = ", ".join(source_fields)
        return f"{prefix} Prioritize filling or falsifying: {missing}."
    return prefix


def _evidence_links(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for idea_id in _string_list(design_brief.get("source_idea_ids")):
        links.append(
            {
                "kind": "source_idea",
                "id": idea_id,
                "label": f"Source idea {idea_id}",
                "source_fields": ["source_idea_ids"],
            }
        )
    lead_idea_id = _clean(design_brief.get("lead_idea_id"))
    if lead_idea_id and lead_idea_id not in {
        link["id"] for link in links if link["kind"] == "source_idea"
    }:
        links.append(
            {
                "kind": "source_idea",
                "id": lead_idea_id,
                "label": f"Lead idea {lead_idea_id}",
                "source_fields": ["lead_idea_id"],
            }
        )
    for signal_id in _string_list(
        design_brief.get("evidence_signals") or design_brief.get("signal_ids")
    ):
        links.append(
            {
                "kind": "signal",
                "id": signal_id,
                "label": f"Signal {signal_id}",
                "source_fields": ["evidence_signals"],
            }
        )
    for insight_id in _string_list(
        design_brief.get("inspiring_insights") or design_brief.get("insight_ids")
    ):
        links.append(
            {
                "kind": "insight",
                "id": insight_id,
                "label": f"Insight {insight_id}",
                "source_fields": ["inspiring_insights"],
            }
        )

    counts = _evidence_counts(design_brief)
    for key in ("signals", "insights", "source_ideas"):
        if counts[key] > 0:
            links.append(
                {
                    "kind": "evidence_count",
                    "id": f"{key}:{counts[key]}",
                    "label": f"{counts[key]} {key.replace('_', ' ')}",
                    "source_fields": ["evidence_counts"],
                }
            )
    links.sort(key=lambda item: (item["kind"], item["id"]))
    return links


def _links_for_fields(
    evidence_links: list[dict[str, Any]], source_fields: list[str]
) -> list[dict[str, Any]]:
    selected = [
        link
        for link in evidence_links
        if set(link["source_fields"]) & set(source_fields)
        or (
            link["kind"] in {"source_idea", "signal", "insight"}
            and any(field in source_fields for field in ("source_idea_ids", "evidence_counts"))
        )
    ]
    if not selected:
        selected = evidence_links[:2]
    return selected[:4]


def _unresolved_assumptions(
    design_brief: dict[str, Any],
    groups: list[dict[str, Any]],
    evidence_links: list[dict[str, Any]],
) -> list[str]:
    unresolved: list[str] = []
    required = (
        (
            "specific_user",
            "Confirm the specific user and the workflow owner who feels the problem.",
        ),
        ("buyer", "Confirm the buyer and whether they control budget or approval."),
        ("workflow_context", "Confirm the target workflow and where the MVP changes behavior."),
        ("validation_plan", "Define the first validation action and pass/fail decision."),
    )
    for field, message in required:
        if not _has_value(design_brief.get(field)):
            unresolved.append(message)
    if not evidence_links:
        unresolved.append(
            "Attach evidence links or source idea lineage before treating assumptions as build-ready."
        )
    for group in groups:
        for assumption in group["assumptions"]:
            if assumption["confidence_level"] == "low":
                unresolved.append(
                    f"Validate low-confidence {group['title'].lower()} assumption: {assumption['statement']}"
                )
    return list(dict.fromkeys(unresolved))


def _next_validation_actions(
    groups: list[dict[str, Any]],
    unresolved_assumptions: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    assumptions = [assumption for group in groups for assumption in group["assumptions"]]
    assumptions.sort(key=lambda item: (_confidence_rank(item["confidence_level"]), item["id"]))
    for assumption in assumptions[:6]:
        actions.append(
            {
                "assumption_id": assumption["id"],
                "group": assumption["group"],
                "confidence_level": assumption["confidence_level"],
                "owner_hint": assumption["owner_hint"],
                "action": assumption["validation_action"],
            }
        )
    if unresolved_assumptions:
        actions.append(
            {
                "assumption_id": "unresolved-01",
                "group": "cross_group",
                "confidence_level": "low",
                "owner_hint": "brief owner",
                "action": unresolved_assumptions[0],
            }
        )
    return actions


def _confidence_rank(level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(level, 3)


def _evidence_counts(design_brief: dict[str, Any]) -> dict[str, int]:
    raw_counts = design_brief.get("evidence_counts")
    if isinstance(raw_counts, dict):
        return {
            "signals": _count(raw_counts.get("signals")),
            "insights": _count(raw_counts.get("insights")),
            "source_ideas": _count(raw_counts.get("source_ideas")),
        }
    return {
        "signals": len(
            _string_list(design_brief.get("evidence_signals") or design_brief.get("signal_ids"))
        ),
        "insights": len(
            _string_list(design_brief.get("inspiring_insights") or design_brief.get("insight_ids"))
        ),
        "source_ideas": len(_string_list(design_brief.get("source_idea_ids"))),
    }


def _user(design_brief: dict[str, Any]) -> str:
    return _clean(design_brief.get("specific_user")) or "the target user"


def _buyer(design_brief: dict[str, Any]) -> str:
    return _clean(design_brief.get("buyer")) or "the target buyer"


def _workflow(design_brief: dict[str, Any]) -> str:
    return _clean(design_brief.get("workflow_context")) or "the target workflow"


def _workaround(design_brief: dict[str, Any]) -> str:
    return _clean(design_brief.get("current_workaround")) or "the current workaround"


def _concept(design_brief: dict[str, Any]) -> str:
    return (
        _clean(design_brief.get("merged_product_concept") or design_brief.get("value_proposition"))
        or "the proposed product concept"
    )


def _tech_approach(design_brief: dict[str, Any]) -> str:
    return (
        _clean(design_brief.get("tech_approach"))
        or "the stated architecture and implementation path"
    )


def _first_customers(design_brief: dict[str, Any]) -> str:
    return (
        _clean(design_brief.get("first_10_customers"))
        or _clean(design_brief.get("domain"))
        or "the first qualified customer segment"
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean(value)] if _clean(value) else []
    if isinstance(value, dict):
        return [_clean(key) for key in value if _clean(key)]
    if isinstance(value, list | tuple | set):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _clean_sentence(value: str) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return "Assumption needs validation."
    return cleaned if cleaned.endswith((".", "?", "!")) else f"{cleaned}."


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _inline_links(links: list[dict[str, Any]]) -> str:
    if not links:
        return "None"
    return ", ".join(f"`{link['kind']}:{link['id']}`" for link in links)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
