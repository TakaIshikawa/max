"""Portfolio cannibalization analysis for ideas and persisted design briefs."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from itertools import combinations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.portfolio_cannibalization.v1"
KIND = "max.portfolio_cannibalization"
DEFAULT_LIMIT = 10_000
DEFAULT_MIN_SCORE = 0.45


def build_portfolio_cannibalization_report(
    store: Store,
    *,
    domain: str | Iterable[str] | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Build a JSON-ready cannibalization report from persisted portfolio records."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    domains = _filter_values(domain)
    if domains and len(domains) == 1:
        domain_filter = next(iter(domains))
        units = store.get_buildable_units(limit=limit, domain=domain_filter)
        briefs = store.get_design_briefs(limit=limit, domain=domain_filter)
    else:
        units = store.get_buildable_units(limit=limit)
        briefs = store.get_design_briefs(limit=limit)

    return build_portfolio_cannibalization_from_records(
        buildable_units=units,
        design_briefs=briefs,
        domain=domains,
        min_score=min_score,
    )


def build_portfolio_cannibalization_from_records(
    *,
    buildable_units: Iterable[Any],
    design_briefs: Iterable[Mapping[str, Any]],
    domain: str | Iterable[str] | set[str] | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    """Find ranked overlap pairs and clusters from already-loaded portfolio records."""

    if not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be between 0 and 1")

    domain_filter = _filter_values(domain)
    records = sorted(
        [
            record
            for record in (
                [_unit_record(unit) for unit in buildable_units]
                + [_brief_record(brief) for brief in design_briefs]
            )
            if _matches_filter(record["domain"], domain_filter)
        ],
        key=lambda record: (record["id"], record["source_type"]),
    )

    pair_findings: list[dict[str, Any]] = []
    adjacency: dict[str, set[str]] = {record["id"]: set() for record in records}
    by_id = {record["id"]: record for record in records}
    for left, right in combinations(records, 2):
        finding = _pair_finding(left, right)
        if finding["score"] < min_score:
            continue
        pair_findings.append(finding)
        adjacency[left["id"]].add(right["id"])
        adjacency[right["id"]].add(left["id"])

    pair_findings.sort(key=lambda item: (-item["score"], item["ids"][0], item["ids"][1]))
    clusters = _clusters(adjacency, by_id=by_id, pair_findings=pair_findings)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "domain": sorted(domain_filter) if domain_filter else None,
            "min_score": min_score,
        },
        "summary": {
            "total_items": len(records),
            "buildable_unit_count": sum(
                1 for record in records if record["source_type"] == "buildable_unit"
            ),
            "design_brief_count": sum(
                1 for record in records if record["source_type"] == "design_brief"
            ),
            "flagged_pair_count": len(pair_findings),
            "cluster_count": len(clusters),
        },
        "pair_findings": pair_findings,
        "clusters": clusters,
        "recommendations": _recommendations(pair_findings, clusters),
    }


def _pair_finding(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    components = {
        "buyer": _jaccard(left["buyer_terms"], right["buyer_terms"]),
        "workflow": _jaccard(left["workflow_terms"], right["workflow_terms"]),
        "market_wedge": _jaccard(left["market_terms"], right["market_terms"]),
        "implementation_scope": _jaccard(left["implementation_terms"], right["implementation_terms"]),
        "problem": _cosine_counts(left["problem_terms"], right["problem_terms"]),
        "solution": _cosine_counts(left["solution_terms"], right["solution_terms"]),
        "evidence_sources": _jaccard(left["evidence_ids"], right["evidence_ids"]),
    }
    components["solution_scope_reinforcement"] = (
        0.10
        if components["solution"] >= 0.75 and components["implementation_scope"] >= 0.35
        else 0.0
    )
    score = round(
        min(
            components["buyer"] * 0.20
            + components["workflow"] * 0.14
            + components["market_wedge"] * 0.08
            + components["implementation_scope"] * 0.22
            + components["problem"] * 0.08
            + components["solution"] * 0.25
            + components["evidence_sources"] * 0.03
            + components["solution_scope_reinforcement"],
            1.0,
        ),
        3,
    )
    reasons = _reasons(left, right, components)
    return {
        "ids": [left["id"], right["id"]],
        "items": [_item_summary(left), _item_summary(right)],
        "score": score,
        "score_components": {key: round(value, 3) for key, value in components.items()},
        "reasons": reasons,
        "differentiation_actions": _differentiation_actions(components, left, right),
    }


def _reasons(
    left: dict[str, Any],
    right: dict[str, Any],
    components: dict[str, float],
) -> list[dict[str, Any]]:
    reason_specs = [
        (
            "buyer",
            "Compete for the same buyer or target user",
            sorted(left["buyer_terms"] & right["buyer_terms"]),
        ),
        (
            "workflow",
            "Attach to the same workflow or workaround",
            sorted(left["workflow_terms"] & right["workflow_terms"]),
        ),
        (
            "market_wedge",
            "Share category, domain, theme, tag, or customer wedge language",
            sorted(left["market_terms"] & right["market_terms"]),
        ),
        (
            "implementation_scope",
            "Depend on similar implementation scope or stack choices",
            sorted(left["implementation_terms"] & right["implementation_terms"]),
        ),
        (
            "problem",
            "Use similar problem statement language",
            sorted(set(left["problem_terms"]) & set(right["problem_terms"])),
        ),
        (
            "solution",
            "Describe similar solution capabilities",
            sorted(set(left["solution_terms"]) & set(right["solution_terms"])),
        ),
        (
            "evidence_sources",
            "Reuse the same source idea or evidence identifiers",
            sorted(left["evidence_ids"] & right["evidence_ids"]),
        ),
    ]
    reasons = [
        {
            "type": reason_type,
            "description": description,
            "score": round(components[reason_type], 3),
            "shared_terms": shared[:12],
        }
        for reason_type, description, shared in reason_specs
        if components[reason_type] > 0.0
    ]
    return sorted(reasons, key=lambda item: (-item["score"], item["type"]))


def _differentiation_actions(
    components: dict[str, float],
    left: dict[str, Any],
    right: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if components["buyer"] >= 0.4:
        actions.append("Assign one item to a narrower buyer, budget owner, or adoption trigger.")
    if components["workflow"] >= 0.35:
        actions.append("Separate the workflow entry points, handoff moments, or success metrics.")
    if components["solution"] >= 0.35 or components["implementation_scope"] >= 0.35:
        actions.append("Split capabilities by must-have scope, integration depth, or delivery surface.")
    if components["market_wedge"] >= 0.45:
        actions.append("Choose distinct market wedges before writing specs or running pilots.")
    if components["evidence_sources"] > 0.0:
        actions.append("Collect independent evidence for each item before advancing both.")
    if not actions:
        actions.append("Review positioning and keep separate only if each item has a distinct validation plan.")
    if left["source_type"] != right["source_type"]:
        actions.append("Reconcile the generated idea and design brief so the brief does not duplicate roadmap scope.")
    return actions


def _clusters(
    adjacency: dict[str, set[str]],
    *,
    by_id: dict[str, dict[str, Any]],
    pair_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_pair = {tuple(finding["ids"]): finding for finding in pair_findings}
    visited: set[str] = set()
    clusters: list[dict[str, Any]] = []
    for item_id in sorted(adjacency):
        if item_id in visited or not adjacency[item_id]:
            continue
        component = _component(item_id, adjacency, visited)
        member_pairs = [
            by_pair[tuple(sorted((left, right)))]
            for left, right in combinations(component, 2)
            if tuple(sorted((left, right))) in by_pair
        ]
        if not member_pairs:
            continue
        score = round(sum(pair["score"] for pair in member_pairs) / len(member_pairs), 3)
        reason_types = sorted(
            {reason["type"] for pair in member_pairs for reason in pair["reasons"]}
        )
        clusters.append(
            {
                "id": "cannibalization-" + "-".join(component[:3]),
                "ids": component,
                "score": score,
                "reason_types": reason_types,
                "representative_items": [
                    _item_summary(by_id[item_id])
                    for item_id in sorted(
                        component,
                        key=lambda value: (
                            -by_id[value]["readiness_score"],
                            by_id[value]["source_type"],
                            value,
                        ),
                    )[:5]
                ],
            }
        )
    return sorted(clusters, key=lambda item: (-item["score"], item["id"]))


def _component(start: str, adjacency: dict[str, set[str]], visited: set[str]) -> list[str]:
    stack = [start]
    component: list[str] = []
    visited.add(start)
    while stack:
        item_id = stack.pop()
        component.append(item_id)
        for neighbor in sorted(adjacency[item_id], reverse=True):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return sorted(component)


def _unit_record(unit: Any) -> dict[str, Any]:
    unit_id = _clean(_get(unit, "id") or _get(unit, "buildable_unit_id") or _get(unit, "idea_id"))
    category = _clean(_get(unit, "category")) or "uncategorized"
    return _record(
        record_id=unit_id,
        title=_clean(_get(unit, "title")) or unit_id,
        source_type="buildable_unit",
        domain=_clean(_get(unit, "domain")) or "unspecified",
        category=category,
        theme=_theme_value(_get(unit, "theme") or category),
        tags=_list(_get(unit, "tags")),
        buyer_text=" ".join(
            [
                _clean(_get(unit, "target_users")),
                _clean(_get(unit, "specific_user")),
                _clean(_get(unit, "buyer")),
                _clean(_get(unit, "first_10_customers")),
            ]
        ),
        workflow_text=" ".join(
            [
                _clean(_get(unit, "workflow_context")),
                _clean(_get(unit, "current_workaround")),
                _clean(_get(unit, "validation_plan")),
            ]
        ),
        problem_text=" ".join(
            [
                _clean(_get(unit, "title")),
                _clean(_get(unit, "one_liner")),
                _clean(_get(unit, "problem")),
                _clean(_get(unit, "value_proposition")),
            ]
        ),
        solution_text=" ".join(
            [
                _clean(_get(unit, "solution")),
                _clean(_get(unit, "tech_approach")),
                " ".join(_flatten(_get(unit, "suggested_stack"))),
                _clean(_get(unit, "composability_notes")),
            ]
        ),
        evidence_ids=[
            unit_id,
            *_list(_get(unit, "source_idea_ids")),
            *_list(_get(unit, "evidence_signals")),
            *_list(_get(unit, "inspiring_insights")),
        ],
        readiness_score=_unit_readiness_score(unit),
    )


def _brief_record(brief: Mapping[str, Any]) -> dict[str, Any]:
    brief_id = _clean(brief.get("id"))
    source_idea_ids = _list(brief.get("source_idea_ids"))
    source_ids = [
        _clean(source.get("idea_id"))
        for source in _list(brief.get("sources"))
        if isinstance(source, Mapping)
    ]
    mvp_scope = _list(brief.get("mvp_scope"))
    return _record(
        record_id=brief_id,
        title=_clean(brief.get("title")) or brief_id,
        source_type="design_brief",
        domain=_clean(brief.get("domain")) or "unspecified",
        category="design_brief",
        theme=_theme_value(brief.get("theme")),
        tags=_list(brief.get("tags")),
        buyer_text=" ".join(
            [
                _clean(brief.get("buyer")),
                _clean(brief.get("specific_user")),
                _clean(brief.get("lead_idea_id")),
            ]
        ),
        workflow_text=" ".join(
            [
                _clean(brief.get("workflow_context")),
                _clean(brief.get("validation_plan")),
                " ".join(_list(brief.get("first_milestones"))),
            ]
        ),
        problem_text=" ".join(
            [
                _clean(brief.get("title")),
                _clean(brief.get("why_this_now")),
                _clean(brief.get("synthesis_rationale")),
            ]
        ),
        solution_text=" ".join(
            [
                _clean(brief.get("merged_product_concept")),
                " ".join(mvp_scope),
            ]
        ),
        evidence_ids=[brief_id, *source_idea_ids, *source_ids],
        readiness_score=_float(brief.get("readiness_score")),
    )


def _record(
    *,
    record_id: str,
    title: str,
    source_type: str,
    domain: str,
    category: str,
    theme: str,
    tags: list[str],
    buyer_text: str,
    workflow_text: str,
    problem_text: str,
    solution_text: str,
    evidence_ids: Iterable[Any],
    readiness_score: float,
) -> dict[str, Any]:
    market_values = [domain, category, theme, *tags]
    implementation_text = " ".join([category, theme, solution_text])
    return {
        "id": record_id,
        "title": title,
        "source_type": source_type,
        "domain": domain,
        "category": category,
        "theme": theme,
        "readiness_score": readiness_score,
        "buyer_terms": set(_tokens(buyer_text)),
        "workflow_terms": set(_tokens(workflow_text)),
        "market_terms": set(_tokens(" ".join(market_values))),
        "implementation_terms": set(_tokens(implementation_text)),
        "problem_terms": _token_counts(problem_text),
        "solution_terms": _token_counts(solution_text),
        "evidence_ids": set(_dedupe(evidence_ids)),
    }


def _item_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "title": record["title"],
        "source_type": record["source_type"],
        "domain": record["domain"],
        "theme": record["theme"],
    }


def _recommendations(
    pair_findings: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not pair_findings:
        return [
            {
                "priority": "low",
                "action": "Continue portfolio generation; no item pair crossed the cannibalization threshold.",
                "rationale": "The current portfolio has enough separation across buyer, workflow, market, and scope signals.",
            }
        ]

    top = pair_findings[0]
    recommendations = [
        {
            "priority": "high",
            "action": f"Differentiate or consolidate {top['ids'][0]} and {top['ids'][1]} before investing in specs.",
            "rationale": f"The pair has the highest cannibalization score ({top['score']}).",
        }
    ]
    if clusters:
        recommendations.append(
            {
                "priority": "medium",
                "action": f"Review cluster {clusters[0]['id']} as a portfolio-level positioning decision.",
                "rationale": f"{len(clusters[0]['ids'])} items are connected by above-threshold overlap.",
            }
        )
    return recommendations


def _unit_readiness_score(unit: Any) -> float:
    quality = _float(_get(unit, "quality_score"))
    usefulness = _float(_get(unit, "usefulness_score"))
    novelty = _float(_get(unit, "novelty_score"))
    score = max(quality, usefulness, novelty) * 10.0
    status = _clean(_get(unit, "status"))
    if status == "published":
        score = max(score, 85.0)
    elif status == "approved":
        score = max(score, 75.0)
    elif status == "evaluated":
        score = max(score, 55.0)
    elif status == "rejected":
        score = min(score, 35.0)
    return round(min(max(score, 0.0), 100.0), 1)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cosine_counts(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in shared)
    left_mag = math.sqrt(sum(count * count for count in left.values()))
    right_mag = math.sqrt(sum(count * count for count in right.values()))
    if left_mag == 0.0 or right_mag == 0.0:
        return 0.0
    return dot / (left_mag * right_mag)


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    ]


def _token_counts(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _theme_value(value: Any) -> str:
    return _clean(value).lower().replace(" ", "-") or "uncategorized"


def _filter_values(value: str | Iterable[str] | set[str] | None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = _clean(value)
        return {cleaned} if cleaned else None
    values = {_clean(item) for item in value}
    values.discard("")
    return values or None


def _matches_filter(value: str, allowed: set[str] | None) -> bool:
    return allowed is None or value in allowed


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _flatten(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        flattened: list[str] = []
        for key, item in value.items():
            flattened.append(str(key))
            flattened.extend(_flatten(item))
        return flattened
    if isinstance(value, list | tuple | set):
        flattened = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    if value in (None, ""):
        return []
    return [str(value)]


def _get(value: Any, field: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clean(value: Any) -> str:
    return str(value or "").strip()


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "both",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "need",
    "needs",
    "no",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}
