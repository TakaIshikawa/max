"""Dependency map analysis for generated buildable units."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from itertools import combinations
from typing import Any

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


SCHEMA_VERSION = "max.unit_dependency_map.v1"


def build_unit_dependency_map(
    store: Store,
    *,
    limit: int = 100,
    min_shared_signals: int = 1,
) -> dict[str, Any]:
    """Build a deterministic dependency map across stored buildable units."""

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if min_shared_signals < 1:
        raise ValueError("min_shared_signals must be at least 1")

    units = sorted(store.get_buildable_units(limit=10_000), key=lambda unit: unit.id)[:limit]
    features = {unit.id: _unit_features(unit) for unit in units}
    nodes = [_node(unit, features[unit.id]) for unit in units]

    edges: list[dict[str, Any]] = []
    for left, right in combinations(units, 2):
        edge = _edge(
            left,
            right,
            left_features=features[left.id],
            right_features=features[right.id],
            min_shared_signals=min_shared_signals,
        )
        if edge is not None:
            edges.append(edge)

    edges.sort(key=lambda item: (item["source"], item["target"]))
    connected_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    clusters = _clusters(units, features, edges, min_shared_signals=min_shared_signals)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.unit_dependency_map",
        "parameters": {
            "limit": limit,
            "min_shared_signals": min_shared_signals,
        },
        "summary": {
            "unit_count": len(nodes),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
            "isolated_unit_count": len([unit for unit in units if unit.id not in connected_ids]),
        },
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters,
        "isolated_units": [unit.id for unit in units if unit.id not in connected_ids],
        "recommended_build_order": _recommended_build_order(units, edges),
    }


def render_unit_dependency_map(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a dependency map report."""

    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    if fmt != "markdown":
        raise ValueError("fmt must be 'markdown' or 'json'")

    summary = report.get("summary", {})
    lines = [
        "# Buildable Unit Dependency Map",
        "",
        "## Summary",
        f"- Units: {summary.get('unit_count', 0)}",
        f"- Edges: {summary.get('edge_count', 0)}",
        f"- Clusters: {summary.get('cluster_count', 0)}",
        f"- Isolated units: {summary.get('isolated_unit_count', 0)}",
        "",
        "## Recommended Build Order",
    ]

    order = report.get("recommended_build_order", [])
    if order:
        lines.extend(f"{index}. {unit_id}" for index, unit_id in enumerate(order, start=1))
    else:
        lines.append("- No buildable units included.")

    lines.extend(["", "## Clusters"])
    clusters = report.get("clusters", [])
    if clusters:
        for cluster in clusters:
            lines.append(
                f"- {cluster['id']} ({cluster['type']}): "
                f"{', '.join(cluster['unit_ids'])} - {cluster['reason']}"
            )
    else:
        lines.append("- No shared dependency clusters found.")

    lines.extend(["", "## Edges"])
    edges = report.get("edges", [])
    if edges:
        for edge in edges:
            reasons = ", ".join(reason["type"] for reason in edge.get("reasons", []))
            lines.append(
                f"- {edge['source']} -> {edge['target']} "
                f"({edge['direction']}, confidence {edge['confidence']:.2f}): {reasons}"
            )
            for reason in edge.get("reasons", []):
                detail = reason["description"]
                shared = reason.get("shared_values") or reason.get("matched_phrase")
                if shared:
                    detail += f" [{_join_values(shared)}]"
                lines.append(f"  - {reason['type']}: {detail}")
    else:
        lines.append("- No dependency edges found.")

    isolated = report.get("isolated_units", [])
    if isolated:
        lines.extend(["", "## Isolated Units", "- " + ", ".join(isolated)])

    return "\n".join(lines) + "\n"


def _node(unit: BuildableUnit, features: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": unit.id,
        "title": unit.title,
        "category": str(unit.category),
        "status": unit.status,
        "target_user": features["target_user"],
        "evidence_signal_ids": sorted(set(unit.evidence_signals)),
        "stack_components": sorted(features["stack"]),
        "prerequisite_terms": sorted(features["prerequisite_terms"]),
    }


def _edge(
    left: BuildableUnit,
    right: BuildableUnit,
    *,
    left_features: dict[str, Any],
    right_features: dict[str, Any],
    min_shared_signals: int,
) -> dict[str, Any] | None:
    reasons: list[dict[str, Any]] = []

    shared_evidence = _ordered_overlap(left.evidence_signals, right.evidence_signals)
    if len(shared_evidence) >= min_shared_signals:
        reasons.append(
            {
                "type": "shared_evidence",
                "description": "Units cite the same source evidence signals.",
                "shared_values": shared_evidence,
                "confidence": min(1.0, 0.45 + 0.1 * len(shared_evidence)),
            }
        )

    shared_stack = sorted(left_features["stack"] & right_features["stack"])
    if shared_stack:
        reasons.append(
            {
                "type": "shared_stack",
                "description": "Units use overlapping stack or implementation components.",
                "shared_values": shared_stack[:12],
                "confidence": min(1.0, 0.35 + 0.05 * len(shared_stack)),
            }
        )

    if (
        left_features["target_user"]
        and left_features["target_user"] == right_features["target_user"]
    ):
        reasons.append(
            {
                "type": "same_target_user",
                "description": "Units name the same target user or buyer.",
                "shared_values": [left_features["target_user"]],
                "confidence": 0.5,
            }
        )

    prerequisite = _prerequisite_reason(left, right, left_features, right_features)
    source = left.id
    target = right.id
    direction = "related"
    if prerequisite is not None:
        prerequisite_source, prerequisite_target, reason = prerequisite
        source = prerequisite_source
        target = prerequisite_target
        direction = "prerequisite"
        reasons.append(reason)

    if not reasons:
        return None

    return {
        "source": source,
        "target": target,
        "direction": direction,
        "confidence": round(min(1.0, sum(reason["confidence"] for reason in reasons) / 1.8), 3),
        "reasons": sorted(reasons, key=lambda reason: reason["type"]),
    }


def _clusters(
    units: list[BuildableUnit],
    features: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    min_shared_signals: int,
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []

    evidence_index: dict[str, list[str]] = defaultdict(list)
    stack_index: dict[str, list[str]] = defaultdict(list)
    user_index: dict[str, list[str]] = defaultdict(list)

    for unit in units:
        for signal_id in sorted(set(unit.evidence_signals)):
            evidence_index[signal_id].append(unit.id)
        for component in sorted(features[unit.id]["stack"]):
            stack_index[component].append(unit.id)
        if features[unit.id]["target_user"]:
            user_index[features[unit.id]["target_user"]].append(unit.id)

    for signal_id, unit_ids in sorted(evidence_index.items()):
        if len(unit_ids) >= 2 and len(unit_ids) >= min_shared_signals:
            clusters.append(
                _cluster(
                    f"evidence:{signal_id}",
                    "shared_evidence",
                    signal_id,
                    unit_ids,
                    f"Shared evidence signal {signal_id}",
                )
            )

    for component, unit_ids in sorted(stack_index.items()):
        if len(unit_ids) >= 2:
            clusters.append(
                _cluster(
                    f"stack:{component}",
                    "shared_stack",
                    component,
                    unit_ids,
                    f"Overlapping stack component {component}",
                )
            )

    for target_user, unit_ids in sorted(user_index.items()):
        if len(unit_ids) >= 2:
            clusters.append(
                _cluster(
                    f"user:{target_user}",
                    "same_target_user",
                    target_user,
                    unit_ids,
                    f"Same target user {target_user}",
                )
            )

    for edge in edges:
        if edge["direction"] != "prerequisite":
            continue
        clusters.append(
            _cluster(
                f"prerequisite:{edge['source']}->{edge['target']}",
                "prerequisite",
                f"{edge['source']} before {edge['target']}",
                [edge["source"], edge["target"]],
                "Prerequisite-like wording indicates build sequence.",
            )
        )

    return sorted(clusters, key=lambda item: (item["type"], item["id"]))


def _cluster(
    cluster_id: str,
    cluster_type: str,
    label: str,
    unit_ids: list[str],
    reason: str,
) -> dict[str, Any]:
    return {
        "id": cluster_id,
        "type": cluster_type,
        "label": label,
        "unit_ids": sorted(unit_ids),
        "reason": reason,
    }


def _recommended_build_order(units: list[BuildableUnit], edges: list[dict[str, Any]]) -> list[str]:
    unit_ids = sorted(unit.id for unit in units)
    outgoing: dict[str, set[str]] = {unit_id: set() for unit_id in unit_ids}
    indegree: dict[str, int] = {unit_id: 0 for unit_id in unit_ids}

    for edge in edges:
        if edge["direction"] != "prerequisite":
            continue
        source = edge["source"]
        target = edge["target"]
        if source not in outgoing or target not in indegree or target in outgoing[source]:
            continue
        outgoing[source].add(target)
        indegree[target] += 1

    ready = sorted(unit_id for unit_id, count in indegree.items() if count == 0)
    order: list[str] = []
    while ready:
        unit_id = ready.pop(0)
        order.append(unit_id)
        for dependent in sorted(outgoing[unit_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort()

    if len(order) != len(unit_ids):
        remaining = [unit_id for unit_id in unit_ids if unit_id not in order]
        order.extend(remaining)
    return order


def _unit_features(unit: BuildableUnit) -> dict[str, Any]:
    text = _unit_text(unit)
    return {
        "target_user": _target_user(unit),
        "stack": set(_stack_components(unit)),
        "title_tokens": set(_tokens(unit.title)),
        "text": text,
        "tokens": set(_tokens(text)),
        "prerequisite_terms": {
            term
            for term in _PREREQUISITE_TERMS
            if re.search(rf"\b{re.escape(term)}\b", text.lower())
        },
    }


def _target_user(unit: BuildableUnit) -> str:
    return _normalize_phrase(unit.specific_user or unit.target_users or unit.buyer)


def _unit_text(unit: BuildableUnit) -> str:
    return " ".join(
        value
        for value in [
            unit.title,
            unit.one_liner,
            unit.problem,
            unit.solution,
            unit.value_proposition,
            unit.workflow_context,
            unit.current_workaround,
            unit.tech_approach,
            unit.composability_notes,
        ]
        if value
    )


def _stack_components(unit: BuildableUnit) -> list[str]:
    values = [unit.tech_approach, unit.composability_notes]
    values.extend(_flatten_stack(unit.suggested_stack))
    tokens = _tokens(" ".join(str(value) for value in values if value))
    return [token for token in tokens if token not in _STACK_STOPWORDS]


def _flatten_stack(value: Any) -> list[str]:
    if isinstance(value, dict):
        flattened: list[str] = []
        for key, item in value.items():
            flattened.append(str(key))
            flattened.extend(_flatten_stack(item))
        return flattened
    if isinstance(value, list | tuple | set):
        flattened = []
        for item in value:
            flattened.extend(_flatten_stack(item))
        return flattened
    if value in (None, ""):
        return []
    return [str(value)]


def _prerequisite_reason(
    left: BuildableUnit,
    right: BuildableUnit,
    left_features: dict[str, Any],
    right_features: dict[str, Any],
) -> tuple[str, str, dict[str, Any]] | None:
    left_depends_on_right = _mentions_dependency(left_features["text"], right_features["title_tokens"])
    right_depends_on_left = _mentions_dependency(right_features["text"], left_features["title_tokens"])

    if left_depends_on_right and not right_depends_on_left:
        return _prerequisite_tuple(
            right.id,
            left.id,
            f"{left.id} uses prerequisite wording that references {right.id}.",
            left_depends_on_right,
        )
    if right_depends_on_left and not left_depends_on_right:
        return _prerequisite_tuple(
            left.id,
            right.id,
            f"{right.id} uses prerequisite wording that references {left.id}.",
            right_depends_on_left,
        )

    left_foundation = bool(left_features["prerequisite_terms"] & _FOUNDATION_TERMS)
    right_foundation = bool(right_features["prerequisite_terms"] & _FOUNDATION_TERMS)
    if left_foundation and not right_foundation and _related(left_features, right_features):
        return _prerequisite_tuple(
            left.id,
            right.id,
            f"{left.id} has foundation-like wording and related implementation context.",
            sorted(left_features["prerequisite_terms"] & _FOUNDATION_TERMS),
        )
    if right_foundation and not left_foundation and _related(left_features, right_features):
        return _prerequisite_tuple(
            right.id,
            left.id,
            f"{right.id} has foundation-like wording and related implementation context.",
            sorted(right_features["prerequisite_terms"] & _FOUNDATION_TERMS),
        )
    return None


def _prerequisite_tuple(
    source: str,
    target: str,
    description: str,
    matched_phrase: str | list[str],
) -> tuple[str, str, dict[str, Any]]:
    return (
        source,
        target,
        {
            "type": "prerequisite_wording",
            "description": description,
            "matched_phrase": matched_phrase,
            "confidence": 0.8,
        },
    )


def _mentions_dependency(text: str, other_title_tokens: set[str]) -> str | None:
    lowered = text.lower()
    if not other_title_tokens or not any(token in _tokens(lowered) for token in other_title_tokens):
        return None
    for pattern in _DEPENDENCY_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0)
    return None


def _related(left_features: dict[str, Any], right_features: dict[str, Any]) -> bool:
    return bool(
        left_features["stack"] & right_features["stack"]
        or (
            left_features["target_user"]
            and left_features["target_user"] == right_features["target_user"]
        )
    )


def _ordered_overlap(left: list[str], right: list[str]) -> list[str]:
    right_set = set(right)
    return [item for item in left if item in right_set]


def _join_values(value: str | list[str]) -> str:
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value)


def _normalize_phrase(text: str) -> str:
    return " ".join(_tokens(text))


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    ]


_DEPENDENCY_PATTERNS = [
    r"\bdepends on\b",
    r"\brequires\b",
    r"\bafter\b",
    r"\bonce\b",
    r"\bbuilds on\b",
    r"\bbuilt on\b",
    r"\busing\b",
]

_PREREQUISITE_TERMS = {
    "after",
    "base",
    "baseline",
    "before",
    "depends",
    "foundation",
    "foundational",
    "prerequisite",
    "requires",
    "shared",
}

_FOUNDATION_TERMS = {"base", "baseline", "foundation", "foundational", "shared"}

_STACK_STOPWORDS = {
    "approach",
    "component",
    "components",
    "implementation",
    "language",
    "runtime",
    "service",
    "stack",
    "with",
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
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
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "tool",
    "tools",
    "unit",
    "units",
    "use",
    "users",
    "with",
}
