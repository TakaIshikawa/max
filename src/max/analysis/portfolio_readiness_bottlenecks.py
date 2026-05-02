"""Portfolio readiness bottleneck analysis for persisted design work."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.portfolio_readiness_bottlenecks.v1"
KIND = "max.portfolio_readiness_bottlenecks"
DEFAULT_LIMIT = 10_000
REPRESENTATIVE_LIMIT = 5
LOW_READINESS_THRESHOLD = 70.0
_CSV_COLUMNS = (
    "bottleneck_id",
    "check_id",
    "category",
    "title",
    "severity",
    "affected_count",
    "portfolio_share",
    "affected_idea_ids",
    "failed_check_ids",
    "recommendation",
    "owner",
    "action",
)


def build_portfolio_readiness_bottlenecks(
    store: Store,
    *,
    status: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Build a JSON-ready report of common execution-readiness blockers."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    units = store.get_buildable_units(limit=limit, status=status)
    briefs = store.get_design_briefs(limit=limit, status=status)
    return _build_from_records(buildable_units=units, design_briefs=briefs, status=status)


def render_portfolio_readiness_bottlenecks(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render readiness bottlenecks as Markdown, deterministic JSON, or CSV."""

    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported portfolio readiness bottlenecks format: {fmt}")
    return _render_markdown(report)


def _build_from_records(
    *,
    buildable_units: Iterable[Any],
    design_briefs: Iterable[Mapping[str, Any]],
    status: str | None,
) -> dict[str, Any]:
    records = sorted(
        [_unit_record(unit) for unit in buildable_units]
        + [_brief_record(brief) for brief in design_briefs],
        key=lambda record: (record["id"], record["source_type"]),
    )
    blockers = _blockers(records)
    summary = _summary(records, blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"status": _clean(status) or None},
        "summary": summary,
        "bottlenecks": blockers,
        "recommendations": _recommendations(blockers, summary),
    }


def _blockers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_category: dict[str, list[dict[str, Any]]] = {config["id"]: [] for config in _CATEGORIES}

    for record in records:
        for category, evidence in _record_blockers(record):
            rows_by_category[category].append({"record": record, "evidence": evidence})

    dependency_rows = _dependency_concentration_rows(records)
    rows_by_category["dependency_concentration"].extend(dependency_rows)

    total_records = len(records)
    buckets: list[dict[str, Any]] = []
    for config in _CATEGORIES:
        category = config["id"]
        rows = rows_by_category[category]
        if not rows:
            continue
        members = [row["record"] for row in rows]
        affected_ids = _dedupe(member["id"] for member in members)
        count = len(affected_ids)
        affected_records = _records_by_id(records, affected_ids)
        evidence_fields = _evidence_fields(rows)
        severity = _severity(count=count, portfolio_share=count / total_records if total_records else 0.0)
        buckets.append(
            {
                "id": f"readiness:{category}",
                "category": category,
                "title": config["title"],
                "count": count,
                "portfolio_share": round(count / total_records, 3) if total_records else 0.0,
                "severity": severity,
                "affected_item_ids": affected_ids,
                "representative_ids": affected_ids[:REPRESENTATIVE_LIMIT],
                "representative_items": _representative_items(affected_records),
                "evidence_fields": evidence_fields,
                "recommended_next_actions": _actions(category, severity),
            }
        )

    return sorted(
        buckets,
        key=lambda bucket: (
            _severity_rank(bucket["severity"]),
            -bucket["count"],
            bucket["category"],
        ),
    )


def _record_blockers(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    blockers: list[tuple[str, dict[str, Any]]] = []
    if not record["evidence_ids"] and not record["evidence_rationale"]:
        blockers.append(
            (
                "evidence_gaps",
                {
                    "item_id": record["id"],
                    "fields": ["evidence_ids", "evidence_rationale"],
                    "reason": "No explicit source evidence or evidence rationale is attached.",
                },
            )
        )
    if not record["validation_plan"] or _weak_validation_plan(record["validation_plan"]):
        blockers.append(
            (
                "validation_gaps",
                {
                    "item_id": record["id"],
                    "fields": ["validation_plan"],
                    "reason": "Validation plan is missing or lacks a concrete test method.",
                },
            )
        )
    if _technical_uncertainty(record):
        blockers.append(
            (
                "technical_uncertainty",
                {
                    "item_id": record["id"],
                    "fields": ["tech_approach", "suggested_stack", "risks"],
                    "reason": "Technical approach, stack, or risk language leaves implementation uncertainty.",
                },
            )
        )
    if _compliance_risk(record):
        blockers.append(
            (
                "compliance_risk",
                {
                    "item_id": record["id"],
                    "fields": ["risks", "domain_risks", "target_users", "buyer"],
                    "reason": "Brief language indicates security, privacy, legal, audit, or regulated-data review.",
                },
            )
        )
    if _customer_ambiguity(record):
        blockers.append(
            (
                "customer_acquisition_ambiguity",
                {
                    "item_id": record["id"],
                    "fields": ["buyer", "specific_user", "target_users", "first_10_customers"],
                    "reason": "Buyer, specific user, or first-customer path is not specific enough for execution handoff.",
                },
            )
        )
    if record["readiness_score"] < LOW_READINESS_THRESHOLD:
        blockers.append(
            (
                "low_readiness_score",
                {
                    "item_id": record["id"],
                    "fields": ["readiness_score", "status"],
                    "readiness_score": record["readiness_score"],
                    "reason": f"Readiness score is below {LOW_READINESS_THRESHOLD:g}.",
                },
            )
        )
    return blockers


def _dependency_concentration_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for dependency in record["dependencies"]:
            grouped.setdefault(dependency, []).append(record)

    rows: list[dict[str, Any]] = []
    for dependency, members in grouped.items():
        affected = sorted(members, key=lambda record: (record["id"], record["source_type"]))
        if len(affected) < 2:
            continue
        for record in affected:
            rows.append(
                {
                    "record": record,
                    "evidence": {
                        "item_id": record["id"],
                        "fields": ["suggested_stack", "tech_approach", "mvp_scope"],
                        "dependency": dependency,
                        "shared_with_count": len(affected),
                        "reason": f"{dependency} appears in {len(affected)} portfolio items.",
                    },
                }
            )
    return rows


def _summary(
    records: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    affected_ids = {item_id for bucket in blockers for item_id in bucket["affected_item_ids"]}
    low_confidence = len(records) < 2 or not blockers
    return {
        "total_items": len(records),
        "buildable_unit_count": sum(1 for record in records if record["source_type"] == "buildable_unit"),
        "design_brief_count": sum(1 for record in records if record["source_type"] == "design_brief"),
        "blocked_item_count": len(affected_ids),
        "bottleneck_category_count": len(blockers),
        "high_severity_count": sum(1 for bucket in blockers if bucket["severity"] == "high"),
        "medium_severity_count": sum(1 for bucket in blockers if bucket["severity"] == "medium"),
        "low_severity_count": sum(1 for bucket in blockers if bucket["severity"] == "low"),
        "low_readiness_item_count": sum(
            1 for record in records if record["readiness_score"] < LOW_READINESS_THRESHOLD
        ),
        "ready_candidate_count": sum(
            1 for record in records if record["readiness_score"] >= LOW_READINESS_THRESHOLD
        ),
        "confidence": "low" if low_confidence else "medium" if len(records) < 5 else "high",
    }


def _unit_record(unit: Any) -> dict[str, Any]:
    unit_id = _clean(_get(unit, "id") or _get(unit, "buildable_unit_id") or _get(unit, "idea_id"))
    evidence_ids = _dedupe(
        [
            *_list(_get(unit, "evidence_signals")),
            *_list(_get(unit, "inspiring_insights")),
            *_list(_get(unit, "source_idea_ids")),
        ]
    )
    dependencies = _extract_dependencies(
        " ".join(
            [
                _clean(_get(unit, "tech_approach")),
                _clean(_get(unit, "solution")),
                _clean(_get(unit, "composability_notes")),
                " ".join(_flatten(_get(unit, "suggested_stack"))),
            ]
        ),
        structured_values=_flatten(_get(unit, "suggested_stack")),
    )
    return {
        "id": unit_id,
        "title": _clean(_get(unit, "title")) or unit_id,
        "source_type": "buildable_unit",
        "status": _clean(_get(unit, "status")),
        "domain": _clean(_get(unit, "domain")) or "unspecified",
        "theme": _theme_value(_get(unit, "category")),
        "readiness_score": _unit_readiness_score(unit),
        "evidence_ids": evidence_ids,
        "evidence_rationale": _clean(_get(unit, "evidence_rationale")),
        "validation_plan": _clean(_get(unit, "validation_plan")),
        "tech_approach": _clean(_get(unit, "tech_approach")),
        "suggested_stack": _flatten(_get(unit, "suggested_stack")),
        "risks": _string_list(_get(unit, "domain_risks")),
        "buyer": _clean(_get(unit, "buyer")),
        "specific_user": _clean(_get(unit, "specific_user")),
        "target_users": _clean(_get(unit, "target_users")),
        "first_10_customers": _clean(_get(unit, "first_10_customers")),
        "dependencies": dependencies,
    }


def _brief_record(brief: Mapping[str, Any]) -> dict[str, Any]:
    brief_id = _clean(brief.get("id"))
    source_idea_ids = _dedupe(
        [
            *_list(brief.get("source_idea_ids")),
            *[
                source.get("idea_id")
                for source in _list(brief.get("sources"))
                if isinstance(source, Mapping)
            ],
        ]
    )
    dependencies = _extract_dependencies(
        " ".join(
            [
                _clean(brief.get("merged_product_concept")),
                _clean(brief.get("synthesis_rationale")),
                _clean(brief.get("validation_plan")),
                " ".join(_string_list(brief.get("mvp_scope"))),
                " ".join(_string_list(brief.get("first_milestones"))),
                " ".join(_flatten(brief.get("suggested_stack"))),
            ]
        ),
        structured_values=[
            *_string_list(brief.get("mvp_scope")),
            *_string_list(brief.get("first_milestones")),
            *_flatten(brief.get("suggested_stack")),
        ],
    )
    return {
        "id": brief_id,
        "title": _clean(brief.get("title")) or brief_id,
        "source_type": "design_brief",
        "status": _clean(brief.get("design_status")),
        "domain": _clean(brief.get("domain")) or "unspecified",
        "theme": _theme_value(brief.get("theme")),
        "readiness_score": _float(brief.get("readiness_score")),
        "evidence_ids": source_idea_ids,
        "evidence_rationale": _clean(brief.get("synthesis_rationale")),
        "validation_plan": _clean(brief.get("validation_plan")),
        "tech_approach": _clean(brief.get("merged_product_concept")),
        "suggested_stack": _flatten(brief.get("suggested_stack")),
        "risks": _string_list(brief.get("risks")),
        "buyer": _clean(brief.get("buyer")),
        "specific_user": _clean(brief.get("specific_user")),
        "target_users": _clean(brief.get("target_users")),
        "first_10_customers": _clean(brief.get("first_10_customers")),
        "dependencies": dependencies,
    }


def _evidence_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        evidence = row["evidence"]
        for field in evidence["fields"]:
            key = (field, _clean(evidence.get("dependency")))
            grouped.setdefault(
                key,
                {
                    "field": field,
                    "count": 0,
                    "item_ids": [],
                    "examples": [],
                },
            )
            grouped[key]["count"] += 1
            grouped[key]["item_ids"].append(evidence["item_id"])
            if len(grouped[key]["examples"]) < 3:
                grouped[key]["examples"].append(evidence["reason"])
            if evidence.get("dependency"):
                grouped[key]["dependency"] = evidence["dependency"]
    for item in grouped.values():
        item["item_ids"] = _dedupe(item["item_ids"])
    return sorted(
        grouped.values(),
        key=lambda item: (-item["count"], item["field"], item.get("dependency", "")),
    )


def _representative_items(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        members,
        key=lambda member: (
            member["readiness_score"],
            member["source_type"],
            member["id"],
        ),
    )
    return [
        {
            "id": member["id"],
            "title": member["title"],
            "source_type": member["source_type"],
            "status": member["status"],
            "readiness_score": member["readiness_score"],
        }
        for member in ranked[:REPRESENTATIVE_LIMIT]
    ]


def _recommendations(
    blockers: list[dict[str, Any]],
    summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    if summary["total_items"] == 0:
        return [
            {
                "priority": "high",
                "action": "Generate or import design briefs and buildable units before assessing readiness bottlenecks.",
                "rationale": "No persisted portfolio items matched the selected filters.",
            }
        ]
    if not blockers:
        return [
            {
                "priority": "low",
                "action": "Keep the current readiness review cadence and rerun after the next portfolio update.",
                "rationale": "No reportable readiness bottlenecks were detected.",
            }
        ]
    top = blockers[0]
    return [
        {
            "priority": "high" if top["severity"] == "high" else "medium",
            "action": top["recommended_next_actions"][0],
            "rationale": (
                f"{top['title']} affects {top['count']} item(s), "
                f"covering {top['portfolio_share']:.1%} of the analyzed portfolio."
            ),
        }
    ]


def _render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    status = report.get("filters", {}).get("status") or "all"
    lines = [
        "# Portfolio Readiness Bottlenecks",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Items analyzed: {summary['total_items']}",
        f"Buildable units: {summary['buildable_unit_count']}",
        f"Design briefs: {summary['design_brief_count']}",
        f"Blocked items: {summary['blocked_item_count']}",
        f"Bottleneck categories: {summary['bottleneck_category_count']}",
        f"Low readiness items: {summary['low_readiness_item_count']}",
        f"Confidence: {summary['confidence']}",
        f"Status filter: {status}",
        "",
        "## Bottleneck Groups",
        "",
    ]
    buckets = list(report.get("bottlenecks", []))
    if not buckets:
        if summary["total_items"] == 0:
            lines.append("- No portfolio items matched the selected filters.")
        else:
            lines.append("- No reportable readiness bottlenecks were detected.")
    else:
        for bucket in buckets:
            lines.extend(
                [
                    f"### {bucket['title']}",
                    "",
                    f"- Count: {bucket['count']}",
                    f"- Portfolio share: {bucket['portfolio_share']:.1%}",
                    f"- Severity: {bucket['severity']}",
                    f"- Representative IDs: {_inline_list(bucket['representative_ids'])}",
                    f"- Recommended next action: {bucket['recommended_next_actions'][0]}",
                    "",
                ]
            )
            for item in bucket["representative_items"]:
                lines.append(
                    f"  - `{item['id']}` ({item['source_type']}, {item['status']}, "
                    f"{item['readiness_score']:.1f}): {item['title']}"
                )
            lines.append("")

    lines.extend(["## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(
            f"- **{recommendation['priority']}**: {recommendation['action']} "
            f"({recommendation['rationale']})"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for bucket in report.get("bottlenecks", []):
        for row in _csv_rows_for_bucket(bucket):
            writer.writerow(row)
    return output.getvalue()


def _csv_rows_for_bucket(bucket: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence_fields = list(bucket.get("evidence_fields") or [])
    failed_check_ids = _csv_join(
        _check_id(bucket, evidence) for evidence in evidence_fields
    )
    recommendation = _first(bucket.get("recommended_next_actions"))
    base = {
        "bottleneck_id": bucket.get("id", ""),
        "category": bucket.get("category", ""),
        "title": bucket.get("title", ""),
        "severity": bucket.get("severity", ""),
        "portfolio_share": bucket.get("portfolio_share", 0.0),
        "failed_check_ids": failed_check_ids,
        "recommendation": recommendation,
        "owner": bucket.get("owner", ""),
        "action": bucket.get("action", recommendation),
    }
    if not evidence_fields:
        return [
            {
                **base,
                "check_id": bucket.get("id", ""),
                "affected_count": bucket.get("count", 0),
                "affected_idea_ids": _csv_join(bucket.get("affected_item_ids")),
            }
        ]
    rows = []
    for evidence in evidence_fields:
        affected_ids = sorted(evidence.get("item_ids") or [])
        rows.append(
            {
                **base,
                "check_id": _check_id(bucket, evidence),
                "affected_count": len(affected_ids),
                "affected_idea_ids": _csv_join(affected_ids),
            }
        )
    return rows


def _check_id(bucket: Mapping[str, Any], evidence: Mapping[str, Any]) -> str:
    parts = [bucket.get("id", ""), evidence.get("field", "")]
    if evidence.get("dependency"):
        parts.append(evidence["dependency"])
    return ":".join(_clean(part).replace(":", "_") for part in parts if _clean(part))


def _technical_uncertainty(record: Mapping[str, Any]) -> bool:
    text = " ".join(
        [
            _clean(record.get("tech_approach")),
            " ".join(_string_list(record.get("risks"))),
        ]
    ).lower()
    if not _clean(record.get("tech_approach")) and record.get("source_type") == "buildable_unit":
        return True
    if not record.get("dependencies") and not record.get("suggested_stack"):
        return True
    return any(term in text for term in _TECHNICAL_UNCERTAINTY_TERMS)


def _compliance_risk(record: Mapping[str, Any]) -> bool:
    text = " ".join(
        [
            " ".join(_string_list(record.get("risks"))),
            _clean(record.get("target_users")),
            _clean(record.get("buyer")),
            _clean(record.get("tech_approach")),
        ]
    ).lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in _COMPLIANCE_TERMS)


def _customer_ambiguity(record: Mapping[str, Any]) -> bool:
    buyer = _clean(record.get("buyer")).lower()
    user = _clean(record.get("specific_user")).lower()
    target = _clean(record.get("target_users")).lower()
    customers = _clean(record.get("first_10_customers")).lower()
    vague = {"", "both", "users", "teams", "operators", "customers", "developers"}
    if buyer in vague or user in vague:
        return True
    if target in vague and not customers:
        return True
    return False


def _weak_validation_plan(value: str) -> bool:
    lowered = value.lower()
    if len(lowered.split()) < 4:
        return True
    return not any(term in lowered for term in _VALIDATION_TERMS)


def _extract_dependencies(text: str, *, structured_values: Iterable[Any] = ()) -> list[str]:
    dependencies: set[str] = set()
    lowered = _clean(text).lower()
    for pattern, canonical in _DEPENDENCY_PATTERNS:
        if re.search(pattern, lowered):
            dependencies.add(canonical)
    for value in structured_values:
        part = _clean(value)
        for pattern, canonical in _DEPENDENCY_PATTERNS:
            if re.search(pattern, part.lower()):
                dependencies.add(canonical)
    return sorted(dependencies, key=lambda value: value.lower())


def _actions(category: str, severity: str) -> list[str]:
    first = {
        "evidence_gaps": "Attach source evidence and evidence rationale before advancing affected items.",
        "validation_gaps": "Define concrete validation plans with method, sample, and success metric.",
        "technical_uncertainty": "Turn technical unknowns into architecture decisions, spikes, or owner-assigned risks.",
        "compliance_risk": "Route affected items through compliance, security, privacy, or legal review before execution.",
        "dependency_concentration": "Assign dependency owners and fallback paths for concentrated platforms before execution.",
        "customer_acquisition_ambiguity": "Name the buyer, specific user, and first-customer path for affected items.",
        "low_readiness_score": "Hold low-readiness items in discovery until the blocking fields improve.",
    }[category]
    if severity == "high":
        return [first, "Block execution-ready handoff until the evidence is updated."]
    return [first]


def _severity(*, count: int, portfolio_share: float) -> str:
    if count >= 3 or (count >= 2 and portfolio_share >= 0.5):
        return "high"
    if count >= 2 or portfolio_share >= 0.34:
        return "medium"
    return "low"


def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 3)


def _records_by_id(records: list[dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    by_id = {record["id"]: record for record in records}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


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


def _theme_value(value: Any) -> str:
    return _clean(value).lower().replace(" ", "-") or "uncategorized"


def _inline_list(values: Iterable[Any]) -> str:
    return ", ".join(_clean(value) for value in values if _clean(value))


def _csv_join(values: Any, *, separator: str = ";") -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values
    try:
        items = list(values)
    except TypeError:
        return _clean(values)
    return separator.join(_clean(item) for item in items if _clean(item))


def _first(values: Any) -> str:
    if isinstance(values, str):
        return values
    try:
        return _clean(next(iter(values)))
    except (StopIteration, TypeError):
        return ""


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


def _get(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    return [_clean(item) for item in _list(value) if _clean(item)]


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


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


_CATEGORIES: tuple[dict[str, str], ...] = (
    {"id": "evidence_gaps", "title": "Evidence Gaps"},
    {"id": "validation_gaps", "title": "Validation Gaps"},
    {"id": "technical_uncertainty", "title": "Technical Uncertainty"},
    {"id": "compliance_risk", "title": "Compliance Risk"},
    {"id": "dependency_concentration", "title": "Dependency Concentration"},
    {"id": "customer_acquisition_ambiguity", "title": "Customer Acquisition Ambiguity"},
    {"id": "low_readiness_score", "title": "Low Readiness Score"},
)

_VALIDATION_TERMS = (
    "interview",
    "pilot",
    "experiment",
    "test",
    "measure",
    "metric",
    "sample",
    "prototype",
    "concierge",
    "survey",
)

_TECHNICAL_UNCERTAINTY_TERMS = (
    "unknown",
    "uncertain",
    "spike",
    "research",
    "prototype",
    "feasibility",
    "scalability",
    "latency",
    "integration risk",
    "migration",
)

_COMPLIANCE_TERMS = (
    "accessibility",
    "audit",
    "compliance",
    "consent",
    "dpa",
    "gdpr",
    "hipaa",
    "legal",
    "patient",
    "payment",
    "privacy",
    "procurement",
    "regulated",
    "security",
    "sox",
    "vendor",
    "wcag",
)

_DEPENDENCY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bgithub\s+actions?\b|\bgithub-action\b", "GitHub Actions"),
    (r"\bfastapi\b", "FastAPI"),
    (r"\breact\b|\breactjs\b", "React"),
    (r"\bnext\.?js\b|\bnextjs\b", "Next.js"),
    (r"\bnode\.?js\b|\bnodejs\b|\bnode\b", "Node.js"),
    (r"\btypescript\b|\bts\b", "TypeScript"),
    (r"\bpython\b", "Python"),
    (r"\bpostgres(?:ql)?\b", "PostgreSQL"),
    (r"\bredis\b", "Redis"),
    (r"\baws\b|\bamazon\s+web\s+services\b", "AWS"),
    (r"\bgcp\b|\bgoogle\s+cloud\b", "Google Cloud"),
    (r"\bazure\b", "Azure"),
    (r"\bdocker\b", "Docker"),
    (r"\bkubernetes\b|\bk8s\b", "Kubernetes"),
    (r"\bterraform\b", "Terraform"),
    (r"\bstripe\b", "Stripe"),
    (r"\bslack\b", "Slack"),
    (r"\bsalesforce\b", "Salesforce"),
    (r"\bservicenow\b", "ServiceNow"),
    (r"\bopsgenie\b", "Opsgenie"),
    (r"\bopenai\b", "OpenAI"),
    (r"\banthropic\b", "Anthropic"),
    (r"\bllm\b|\bllms\b", "LLM"),
    (r"\boauth\b", "OAuth"),
    (r"\bsso\b", "SSO"),
    (r"\bwebhooks?\b", "Webhooks"),
)
