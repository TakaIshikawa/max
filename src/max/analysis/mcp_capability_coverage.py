"""MCP ecosystem capability coverage analysis."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from max.store.db import Store

DEFAULT_MIN_COUNT = 2
DEFAULT_LIMIT_REPRESENTATIVES = 3
MCP_SOURCE_ADAPTERS = {"mcp_registry", "npm_registry", "github", "awesome_lists"}

CAPABILITY_CATEGORIES = (
    "filesystem",
    "browser",
    "ci_cd",
    "observability",
    "healthcare",
    "finance",
    "security",
    "data",
    "unknown",
)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "filesystem": (
        "file",
        "files",
        "filesystem",
        "file system",
        "directory",
        "directories",
        "folder",
        "local disk",
        "storage",
        "s3",
    ),
    "browser": (
        "browser",
        "chrome",
        "chromium",
        "playwright",
        "selenium",
        "web automation",
        "scrape",
        "scraping",
        "puppeteer",
    ),
    "ci_cd": (
        "ci/cd",
        "ci cd",
        "continuous integration",
        "continuous delivery",
        "github actions",
        "gitlab ci",
        "pipeline",
        "buildkite",
        "jenkins",
        "deployment",
        "deploy",
    ),
    "observability": (
        "observability",
        "monitoring",
        "metrics",
        "metric",
        "logs",
        "logging",
        "tracing",
        "trace",
        "opentelemetry",
        "prometheus",
        "grafana",
        "datadog",
    ),
    "healthcare": (
        "healthcare",
        "health care",
        "clinical",
        "clinician",
        "patient",
        "ehr",
        "emr",
        "fhir",
        "hipaa",
        "medical",
        "hospital",
    ),
    "finance": (
        "finance",
        "financial",
        "fintech",
        "banking",
        "bank",
        "payments",
        "payment",
        "invoice",
        "invoicing",
        "accounting",
        "ledger",
        "trading",
        "portfolio",
    ),
    "security": (
        "security",
        "secure",
        "vulnerability",
        "vulnerabilities",
        "cve",
        "sast",
        "secret",
        "secrets",
        "auth",
        "oauth",
        "iam",
        "compliance",
        "audit",
        "threat",
    ),
    "data": (
        "data",
        "database",
        "postgres",
        "postgresql",
        "mysql",
        "sqlite",
        "warehouse",
        "snowflake",
        "bigquery",
        "analytics",
        "etl",
        "csv",
        "spreadsheet",
        "vector db",
    ),
}


@dataclass(frozen=True)
class MCPCapabilityCategory:
    """Coverage metrics for one capability category."""

    category: str
    total_count: int
    percentage: float
    source_adapters: dict[str, int]
    representative_signal_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "total_count": self.total_count,
            "percentage": self.percentage,
            "source_adapters": self.source_adapters,
            "representative_signal_ids": self.representative_signal_ids,
        }


@dataclass(frozen=True)
class MCPCapabilitySourceAdapter:
    """Overall coverage contribution for one source adapter."""

    source_adapter: str
    total_count: int
    percentage: float
    categories: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_adapter": self.source_adapter,
            "total_count": self.total_count,
            "percentage": self.percentage,
            "categories": self.categories,
        }


@dataclass(frozen=True)
class MCPCapabilityCoverageReport:
    """Capability coverage report for MCP-related signals."""

    generated_at: str
    domain: str | None
    min_count: int
    limit_representatives: int
    source_adapter_filter: str | None
    total_signals: int
    category_percentages: dict[str, float]
    categories: list[MCPCapabilityCategory]
    undercovered_categories: list[str]
    top_source_adapters: list[MCPCapabilitySourceAdapter]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "domain": self.domain,
            "min_count": self.min_count,
            "limit_representatives": self.limit_representatives,
            "source_adapter_filter": self.source_adapter_filter,
            "total_signals": self.total_signals,
            "category_percentages": self.category_percentages,
            "categories": [category.to_dict() for category in self.categories],
            "undercovered_categories": self.undercovered_categories,
            "top_source_adapters": [adapter.to_dict() for adapter in self.top_source_adapters],
        }


def build_mcp_capability_coverage_report(
    store: Store,
    *,
    domain: str | None = None,
    min_count: int = DEFAULT_MIN_COUNT,
    limit_representatives: int = DEFAULT_LIMIT_REPRESENTATIVES,
    source_adapter: str | None = None,
) -> MCPCapabilityCoverageReport:
    """Return deterministic capability coverage for active MCP ecosystem signals."""
    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    if limit_representatives < 0:
        raise ValueError("limit_representatives must be at least 0")

    domain_filter = _normalize_filter(domain)
    source_adapter_filter = _normalize_filter(source_adapter)
    signals = [
        signal
        for signal in _active_signal_records(store, source_adapter=source_adapter_filter)
        if _is_mcp_related(signal) and _matches_domain(signal, domain_filter)
    ]

    category_counts: Counter[str] = Counter()
    adapter_counts: Counter[str] = Counter()
    category_adapter_counts: dict[str, Counter[str]] = {
        category: Counter() for category in CAPABILITY_CATEGORIES
    }
    adapter_category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    representatives: dict[str, list[str]] = {category: [] for category in CAPABILITY_CATEGORIES}

    for signal in signals:
        category = classify_mcp_capability(signal)
        source = str(signal.get("source_adapter") or "unknown")
        category_counts[category] += 1
        adapter_counts[source] += 1
        category_adapter_counts[category][source] += 1
        adapter_category_counts[source][category] += 1
        if len(representatives[category]) < limit_representatives:
            representatives[category].append(str(signal["id"]))

    total = len(signals)
    category_percentages = {
        category: _percentage(category_counts[category], total)
        for category in CAPABILITY_CATEGORIES
    }

    categories = [
        MCPCapabilityCategory(
            category=category,
            total_count=category_counts[category],
            percentage=category_percentages[category],
            source_adapters=dict(sorted(category_adapter_counts[category].items())),
            representative_signal_ids=representatives[category],
        )
        for category in CAPABILITY_CATEGORIES
    ]
    undercovered = [
        category
        for category in CAPABILITY_CATEGORIES
        if category_counts[category] < min_count
    ]
    top_source_adapters = [
        MCPCapabilitySourceAdapter(
            source_adapter=adapter,
            total_count=count,
            percentage=_percentage(count, total),
            categories=dict(sorted(adapter_category_counts[adapter].items())),
        )
        for adapter, count in sorted(adapter_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return MCPCapabilityCoverageReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        domain=domain_filter,
        min_count=min_count,
        limit_representatives=limit_representatives,
        source_adapter_filter=source_adapter_filter,
        total_signals=total,
        category_percentages=category_percentages,
        categories=categories,
        undercovered_categories=undercovered,
        top_source_adapters=top_source_adapters,
    )


def classify_mcp_capability(signal: dict[str, Any]) -> str:
    """Classify a signal into exactly one deterministic MCP capability category."""
    text = _signal_text(signal)
    scores = {
        category: sum(1 for keyword in keywords if keyword in text)
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score <= 0:
        return "unknown"
    for category in CAPABILITY_CATEGORIES:
        if scores.get(category) == best_score:
            return category
    return "unknown"


def _active_signal_records(
    store: Store,
    *,
    source_adapter: str | None,
) -> list[dict[str, Any]]:
    query = """SELECT id, source_type, source_adapter, title, content, tags, metadata
               FROM signals
               WHERE archived_at IS NULL"""
    params: list[Any] = []
    if source_adapter:
        query += " AND source_adapter = ?"
        params.append(source_adapter)
    query += " ORDER BY fetched_at DESC, id DESC"

    rows = store.conn.execute(query, params).fetchall()
    return [
        {
            "id": row["id"],
            "source_type": row["source_type"],
            "source_adapter": row["source_adapter"],
            "title": row["title"],
            "content": row["content"],
            "tags": _json_value(row["tags"], []),
            "metadata": _json_value(row["metadata"], {}),
        }
        for row in rows
    ]


def _is_mcp_related(signal: dict[str, Any]) -> bool:
    adapter = str(signal.get("source_adapter") or "")
    text = _signal_text(signal)
    return adapter in MCP_SOURCE_ADAPTERS or "mcp" in text or "model context protocol" in text


def _matches_domain(signal: dict[str, Any], domain: str | None) -> bool:
    if not domain:
        return True
    return domain in _signal_text(signal)


def _signal_text(signal: dict[str, Any]) -> str:
    metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    chunks = [
        signal.get("title", ""),
        signal.get("content", ""),
        " ".join(str(tag) for tag in signal.get("tags", [])),
        json.dumps(metadata, sort_keys=True),
    ]
    return " ".join(str(chunk) for chunk in chunks if chunk).casefold()


def _json_value(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _normalize_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized.casefold() or None


def _percentage(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 1)
