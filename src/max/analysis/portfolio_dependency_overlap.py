"""Portfolio dependency overlap analysis for design briefs and buildable units."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.portfolio_dependency_overlap.v1"
KIND = "max.portfolio_dependency_overlap"
DEFAULT_LIMIT = 10_000
DEFAULT_MIN_COUNT = 2
DEFAULT_HIGH_OVERLAP_COUNT = 3


def build_portfolio_dependency_overlap_report(
    store: Store,
    *,
    domain: str | Iterable[str] | None = None,
    min_count: int = DEFAULT_MIN_COUNT,
    limit: int = DEFAULT_LIMIT,
    high_overlap_count: int = DEFAULT_HIGH_OVERLAP_COUNT,
) -> dict[str, Any]:
    """Build a JSON-ready dependency overlap report from persisted records."""

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

    return build_portfolio_dependency_overlap_from_records(
        buildable_units=units,
        design_briefs=briefs,
        domain=domains,
        min_count=min_count,
        high_overlap_count=high_overlap_count,
    )


def build_portfolio_dependency_overlap_from_records(
    *,
    buildable_units: Iterable[Any],
    design_briefs: Iterable[Mapping[str, Any]],
    domain: str | Iterable[str] | set[str] | None = None,
    min_count: int = DEFAULT_MIN_COUNT,
    high_overlap_count: int = DEFAULT_HIGH_OVERLAP_COUNT,
) -> dict[str, Any]:
    """Group already-loaded portfolio records by shared dependencies and tooling."""

    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    if high_overlap_count < 2:
        raise ValueError("high_overlap_count must be at least 2")

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

    buckets = _dependency_buckets(
        records,
        min_count=min_count,
        high_overlap_count=high_overlap_count,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "domain": sorted(domain_filter) if domain_filter else None,
            "min_count": min_count,
            "high_overlap_count": high_overlap_count,
        },
        "summary": {
            "total_items": len(records),
            "buildable_unit_count": sum(
                1 for record in records if record["source_type"] == "buildable_unit"
            ),
            "design_brief_count": sum(
                1 for record in records if record["source_type"] == "design_brief"
            ),
            "dependency_bucket_count": len(buckets),
            "high_risk_dependency_count": sum(
                1 for bucket in buckets if bucket["concentration_risk_level"] == "high"
            ),
            "medium_risk_dependency_count": sum(
                1 for bucket in buckets if bucket["concentration_risk_level"] == "medium"
            ),
        },
        "dependency_buckets": buckets,
        "recommendations": _recommendations(buckets, len(records), min_count),
    }


def render_portfolio_dependency_overlap(
    report: Mapping[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a dependency overlap report as Markdown or deterministic JSON."""

    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported portfolio dependency overlap format: {fmt}")
    return render_portfolio_dependency_overlap_markdown(report)


def render_portfolio_dependency_overlap_markdown(report: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown summary of dependency concentration."""

    summary = report["summary"]
    filters = report.get("filters", {})
    lines = [
        "# Portfolio Dependency Overlap",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Items analyzed: {summary['total_items']}",
        f"Buildable units: {summary['buildable_unit_count']}",
        f"Design briefs: {summary['design_brief_count']}",
        f"Shared dependency buckets: {summary['dependency_bucket_count']}",
        f"Domain filter: {_inline_list(filters.get('domain') or []) or 'all'}",
        "",
        "## Dependency Buckets",
        "",
    ]

    buckets = list(report.get("dependency_buckets", []))
    if not buckets:
        if summary["total_items"] == 0:
            lines.append("- No portfolio items matched the selected filters.")
        else:
            min_count = filters.get("min_count", DEFAULT_MIN_COUNT)
            lines.append(f"- No dependency or tooling appeared in at least {min_count} items.")
    else:
        for bucket in buckets:
            lines.extend(
                [
                    f"### {bucket['dependency_name']}",
                    "",
                    f"- Overlap count: {bucket['overlap_count']}",
                    f"- Affected items: {_inline_list(bucket['affected_item_ids'])}",
                    f"- Portfolio share: {bucket['portfolio_share']:.1%}",
                    f"- Concentration risk: {bucket['concentration_risk_level']}",
                    f"- Recommended action: {bucket['recommended_action']}",
                    f"- Domains: {_inline_list(bucket['domains'])}",
                    f"- Source types: {_source_type_summary(bucket['source_type_counts'])}",
                    "",
                ]
            )
            for item in bucket["representative_items"]:
                lines.append(
                    f"  - `{item['id']}` ({item['source_type']}): {item['title']}"
                )
            lines.append("")

    lines.extend(["## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(
            f"- **{recommendation['priority']}**: {recommendation['action']} "
            f"({recommendation['rationale']})"
        )

    return "\n".join(lines).rstrip() + "\n"


def _dependency_buckets(
    records: list[dict[str, Any]],
    *,
    min_count: int,
    high_overlap_count: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for dependency in record["dependencies"]:
            grouped.setdefault(dependency, []).append(record)

    total_records = len(records)
    buckets: list[dict[str, Any]] = []
    for dependency, members in grouped.items():
        if len(members) < min_count:
            continue
        source_type_counts = Counter(member["source_type"] for member in members)
        domain_counts = Counter(member["domain"] for member in members)
        overlap_count = len(members)
        portfolio_share = round(overlap_count / total_records, 3) if total_records else 0.0
        risk_level = _risk_level(
            overlap_count=overlap_count,
            portfolio_share=portfolio_share,
            high_overlap_count=high_overlap_count,
        )
        buckets.append(
            {
                "id": _bucket_id(dependency),
                "dependency_name": dependency,
                "overlap_count": overlap_count,
                "affected_item_ids": [member["id"] for member in members],
                "portfolio_share": portfolio_share,
                "concentration_risk_level": risk_level,
                "recommended_action": _recommended_action(dependency, risk_level, overlap_count),
                "domains": [item["domain"] for item in _counter_rows(domain_counts, "domain")],
                "source_type_counts": _counter_rows(source_type_counts, "source_type"),
                "representative_items": _representative_items(members),
            }
        )

    return sorted(
        buckets,
        key=lambda bucket: (
            _risk_rank(bucket["concentration_risk_level"]),
            -bucket["overlap_count"],
            bucket["dependency_name"].lower(),
        ),
    )


def _unit_record(unit: Any) -> dict[str, Any]:
    unit_id = _clean(_get(unit, "id") or _get(unit, "buildable_unit_id") or _get(unit, "idea_id"))
    category = _clean(_get(unit, "category")) or "uncategorized"
    text_fields = [
        _clean(_get(unit, "title")),
        _clean(_get(unit, "one_liner")),
        _clean(_get(unit, "solution")),
        _clean(_get(unit, "tech_approach")),
        _clean(_get(unit, "composability_notes")),
        " ".join(_flatten(_get(unit, "suggested_stack"))),
    ]
    return {
        "id": unit_id,
        "title": _clean(_get(unit, "title")) or unit_id,
        "source_type": "buildable_unit",
        "domain": _clean(_get(unit, "domain")) or "unspecified",
        "theme": _theme_value(_get(unit, "theme") or category),
        "dependencies": _extract_dependencies(
            " ".join(text_fields),
            structured_values=_flatten(_get(unit, "suggested_stack")),
        ),
        "readiness_score": _unit_readiness_score(unit),
    }


def _brief_record(brief: Mapping[str, Any]) -> dict[str, Any]:
    brief_id = _clean(brief.get("id"))
    mvp_scope = _list(brief.get("mvp_scope"))
    text_fields = [
        _clean(brief.get("title")),
        _clean(brief.get("merged_product_concept")),
        _clean(brief.get("synthesis_rationale")),
        _clean(brief.get("validation_plan")),
        " ".join(_list(brief.get("first_milestones"))),
        " ".join(mvp_scope),
        " ".join(_list(brief.get("risks"))),
        " ".join(_flatten(brief.get("suggested_stack"))),
    ]
    structured_values = [
        *mvp_scope,
        *_list(brief.get("first_milestones")),
        *_flatten(brief.get("suggested_stack")),
    ]
    return {
        "id": brief_id,
        "title": _clean(brief.get("title")) or brief_id,
        "source_type": "design_brief",
        "domain": _clean(brief.get("domain")) or "unspecified",
        "theme": _theme_value(brief.get("theme")),
        "dependencies": _extract_dependencies(
            " ".join(text_fields),
            structured_values=structured_values,
        ),
        "readiness_score": _float(brief.get("readiness_score")),
    }


def _extract_dependencies(text: str, *, structured_values: Iterable[Any] = ()) -> list[str]:
    dependencies: set[str] = set()
    corpus = _clean(text)
    lowered = corpus.lower()
    for pattern, canonical in _DEPENDENCY_PATTERNS:
        if re.search(pattern, lowered):
            dependencies.add(canonical)

    for value in structured_values:
        for part in _dependency_parts(value):
            canonical = _canonical_dependency(part)
            if canonical:
                dependencies.add(canonical)

    return sorted(dependencies, key=lambda value: value.lower())


def _dependency_parts(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    normalized = re.sub(r"[_/|]+", ",", text)
    normalized = re.sub(r"\s+(?:and|with|plus)\s+", ",", normalized, flags=re.I)
    return [part.strip(" .:-") for part in normalized.split(",") if part.strip(" .:-")]


def _canonical_dependency(value: str) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    for pattern, canonical in _DEPENDENCY_PATTERNS:
        if re.fullmatch(pattern, lowered) or re.search(pattern, lowered):
            return canonical
    if lowered in _GENERIC_STACK_TERMS:
        return ""
    if len(lowered) <= 2 or len(lowered.split()) > 4:
        return ""
    if not re.search(r"[a-z]", lowered):
        return ""
    return _title_dependency(cleaned)


def _risk_level(*, overlap_count: int, portfolio_share: float, high_overlap_count: int) -> str:
    if overlap_count >= high_overlap_count or (overlap_count >= 2 and portfolio_share >= 0.6):
        return "high"
    if overlap_count >= 2:
        return "medium"
    return "low"


def _recommended_action(dependency: str, risk_level: str, overlap_count: int) -> str:
    if risk_level == "high":
        return (
            f"Create an owner, fallback path, and version policy for {dependency} before "
            f"advancing the {overlap_count} affected items."
        )
    if risk_level == "medium":
        return (
            f"Confirm whether {dependency} should be standardized for reuse or isolated by item."
        )
    return f"Track {dependency} during the next portfolio review."


def _recommendations(
    buckets: list[dict[str, Any]],
    total_records: int,
    min_count: int,
) -> list[dict[str, str]]:
    if total_records == 0:
        return [
            {
                "priority": "high",
                "action": "Generate or import design briefs and buildable units before assessing dependency overlap.",
                "rationale": "No persisted portfolio items matched the selected filters.",
            }
        ]
    if not buckets:
        return [
            {
                "priority": "low",
                "action": f"No dependency appeared in at least {min_count} portfolio items.",
                "rationale": "The current portfolio does not show shared platform concentration at the selected threshold.",
            }
        ]

    top = buckets[0]
    priority = "high" if top["concentration_risk_level"] == "high" else "medium"
    recommendations = [
        {
            "priority": priority,
            "action": top["recommended_action"],
            "rationale": (
                f"{top['dependency_name']} appears in {top['overlap_count']} item(s), "
                f"covering {top['portfolio_share']:.1%} of the analyzed portfolio."
            ),
        }
    ]
    reusable = [
        bucket
        for bucket in buckets
        if bucket["concentration_risk_level"] != "high" and bucket["overlap_count"] >= 2
    ]
    if reusable:
        recommendations.append(
            {
                "priority": "medium",
                "action": f"Evaluate {reusable[0]['dependency_name']} as a shared implementation accelerator.",
                "rationale": "Moderate overlap can indicate useful reuse rather than concentration risk.",
            }
        )
    return recommendations


def _representative_items(members: list[dict[str, Any]]) -> list[dict[str, str]]:
    ranked = sorted(
        members,
        key=lambda member: (
            -member["readiness_score"],
            member["source_type"],
            member["id"],
        ),
    )
    return [
        {
            "id": member["id"],
            "title": member["title"],
            "source_type": member["source_type"],
            "domain": member["domain"],
            "theme": member["theme"],
        }
        for member in ranked[:5]
    ]


def _counter_rows(counts: Counter[str], key: str) -> list[dict[str, Any]]:
    return [
        {key: value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _source_type_summary(rows: Iterable[Mapping[str, Any]]) -> str:
    return ", ".join(f"{row['source_type']}={row['count']}" for row in rows) or "none"


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


def _bucket_id(dependency: str) -> str:
    return "dependency:" + re.sub(r"[^a-z0-9]+", "-", dependency.lower()).strip("-")


def _risk_rank(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 3)


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


def _inline_list(values: Iterable[Any]) -> str:
    return ", ".join(_clean(value) for value in values if _clean(value))


def _title_dependency(value: str) -> str:
    overrides = {
        "api": "API",
        "aws": "AWS",
        "cli": "CLI",
        "css": "CSS",
        "gcp": "GCP",
        "html": "HTML",
        "llm": "LLM",
        "mcp": "MCP",
        "oauth": "OAuth",
        "sso": "SSO",
        "ui": "UI",
    }
    words = re.split(r"([\s-]+)", value.strip())
    return "".join(overrides.get(word.lower(), word.capitalize()) for word in words)


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


_DEPENDENCY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bgithub\s+actions?\b|\bgithub-action\b", "GitHub Actions"),
    (r"\bgithub\b", "GitHub"),
    (r"\bgitlab\b", "GitLab"),
    (r"\bbitbucket\b", "Bitbucket"),
    (r"\bfastapi\b", "FastAPI"),
    (r"\bdjango\b", "Django"),
    (r"\bflask\b", "Flask"),
    (r"\breact\b|\breactjs\b", "React"),
    (r"\bnext\.?js\b|\bnextjs\b", "Next.js"),
    (r"\bvue\b|\bvue\.?js\b", "Vue.js"),
    (r"\bsvelte\b", "Svelte"),
    (r"\bnode\.?js\b|\bnodejs\b|\bnode\b", "Node.js"),
    (r"\btypescript\b|\bts\b", "TypeScript"),
    (r"\bjavascript\b|\bjs\b", "JavaScript"),
    (r"\bpython\b", "Python"),
    (r"\bgo\b|\bgolang\b", "Go"),
    (r"\brust\b", "Rust"),
    (r"\bpostgres(?:ql)?\b", "PostgreSQL"),
    (r"\bmysql\b", "MySQL"),
    (r"\bsqlite\b", "SQLite"),
    (r"\bredis\b", "Redis"),
    (r"\bsnowflake\b", "Snowflake"),
    (r"\bbigquery\b", "BigQuery"),
    (r"\bdynamodb\b", "DynamoDB"),
    (r"\bmongodb\b", "MongoDB"),
    (r"\bkafka\b", "Kafka"),
    (r"\brabbitmq\b", "RabbitMQ"),
    (r"\bs3\b|\bamazon\s+s3\b", "Amazon S3"),
    (r"\baws\b|\bamazon\s+web\s+services\b", "AWS"),
    (r"\bgcp\b|\bgoogle\s+cloud\b", "Google Cloud"),
    (r"\bazure\b", "Azure"),
    (r"\bdocker\b", "Docker"),
    (r"\bkubernetes\b|\bk8s\b", "Kubernetes"),
    (r"\bterraform\b", "Terraform"),
    (r"\bvercel\b", "Vercel"),
    (r"\bstripe\b", "Stripe"),
    (r"\bslack\b", "Slack"),
    (r"\bsalesforce\b", "Salesforce"),
    (r"\bjira\b", "Jira"),
    (r"\blinear\b", "Linear"),
    (r"\bzendesk\b", "Zendesk"),
    (r"\bservicenow\b", "ServiceNow"),
    (r"\bopsgenie\b", "Opsgenie"),
    (r"\bopenai\b", "OpenAI"),
    (r"\banthropic\b", "Anthropic"),
    (r"\bclaude\b", "Claude"),
    (r"\bllm\b|\bllms\b", "LLM"),
    (r"\boauth\b", "OAuth"),
    (r"\bsso\b", "SSO"),
    (r"\bwebhooks?\b", "Webhooks"),
    (r"\brest\b", "REST API"),
    (r"\bgraphql\b", "GraphQL"),
)

_GENERIC_STACK_TERMS = {
    "adapter",
    "api",
    "application",
    "backend",
    "cli",
    "database",
    "frontend",
    "framework",
    "host",
    "hosting",
    "integration",
    "language",
    "library",
    "runtime",
    "service",
    "stack",
    "storage",
    "surface",
    "tool",
    "tooling",
    "web",
    "worker",
}
