"""OpenAPI-to-MCP candidate discovery report."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from max.store.db import Store
from max.types.signal import Signal

DEFAULT_SIGNAL_LIMIT = 10_000
DEFAULT_MIN_SCORE = 0.0

OPENAPI_SOURCE_ADAPTERS = {
    "apis_guru",
    "github",
    "github_issues",
    "github_discussions",
    "github_releases",
    "awesome_lists",
    "stackoverflow",
}
MCP_COVERAGE_ADAPTERS = {"mcp_registry", "npm_registry", "github", "awesome_lists"}

_DEMAND_KEYWORDS = (
    "agent",
    "agents",
    "automation",
    "workflow",
    "integration",
    "integrations",
    "sdk",
    "client",
    "developer",
    "developers",
    "enterprise",
    "github",
    "popular",
    "requested",
    "support",
)
_COMPLEXITY_HIGH_KEYWORDS = (
    "oauth",
    "saml",
    "hipaa",
    "pci",
    "financial",
    "payment",
    "payments",
    "write",
    "mutating",
    "webhook",
    "webhooks",
    "streaming",
    "realtime",
    "real-time",
)
_GENERIC_TOKENS = {
    "api",
    "apis",
    "openapi",
    "swagger",
    "rest",
    "json",
    "service",
    "services",
    "cloud",
    "platform",
    "server",
    "mcp",
    "model",
    "context",
    "protocol",
    "the",
    "and",
    "for",
    "with",
}


@dataclass(frozen=True)
class OpenAPIMCPCandidateScoreComponent:
    """Named contribution to candidate score."""

    name: str
    score: float
    weight: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class OpenAPIMCPCandidate:
    """Ranked OpenAPI-to-MCP candidate."""

    provider: str
    api_name: str
    domain: str
    score: float
    rank: int
    existing_mcp_coverage: bool
    coverage_signal_ids: list[str] = field(default_factory=list)
    evidence_signal_ids: list[str] = field(default_factory=list)
    source_adapters: dict[str, int] = field(default_factory=dict)
    score_components: list[OpenAPIMCPCandidateScoreComponent] = field(default_factory=list)
    implementation_complexity: str = "medium"
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "api_name": self.api_name,
            "domain": self.domain,
            "score": self.score,
            "rank": self.rank,
            "existing_mcp_coverage": self.existing_mcp_coverage,
            "coverage_signal_ids": self.coverage_signal_ids,
            "evidence_signal_ids": self.evidence_signal_ids,
            "source_adapters": self.source_adapters,
            "score_components": [component.to_dict() for component in self.score_components],
            "implementation_complexity": self.implementation_complexity,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class OpenAPIMCPCandidateReport:
    """OpenAPI-to-MCP candidate report."""

    generated_at: str
    domain: str | None
    min_score: float
    total_candidates: int
    candidates: list[OpenAPIMCPCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "domain": self.domain,
            "min_score": self.min_score,
            "total_candidates": self.total_candidates,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass
class _Cluster:
    provider: str
    api_name: str
    domain: str
    signals: dict[str, Signal] = field(default_factory=dict)
    coverage: dict[str, Signal] = field(default_factory=dict)


def build_openapi_mcp_candidate_report(
    store: Store,
    *,
    domain: str | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
    signal_limit: int = DEFAULT_SIGNAL_LIMIT,
) -> OpenAPIMCPCandidateReport:
    """Return deterministic OpenAPI/API surfaces worth considering for MCP conversion."""
    if min_score < 0 or min_score > 100:
        raise ValueError("min_score must be between 0 and 100")
    if signal_limit < 1:
        raise ValueError("signal_limit must be at least 1")

    domain_filter = _normalize_filter(domain)
    signals = sorted(store.get_signals(limit=signal_limit), key=lambda signal: signal.id)
    api_signals = [signal for signal in signals if _is_openapi_signal(signal)]
    mcp_signals = [signal for signal in signals if _is_mcp_signal(signal)]

    clusters: dict[str, _Cluster] = {}
    for signal in api_signals:
        if not _is_candidate_seed_signal(signal):
            continue
        provider = _provider(signal)
        api_name = _api_name(signal)
        if not provider and not api_name:
            continue
        provider = provider or api_name
        api_name = api_name or provider
        cluster = clusters.setdefault(
            _cluster_key(provider, api_name),
            _Cluster(provider=provider, api_name=api_name, domain=_domain(signal, provider)),
        )
        cluster.signals[signal.id] = signal
        if cluster.domain == "unknown":
            cluster.domain = _domain(signal, provider)

    for signal in signals:
        if _is_mcp_signal(signal):
            continue
        for cluster in clusters.values():
            if signal.id in cluster.signals:
                continue
            if _matches_cluster(signal, cluster):
                cluster.signals[signal.id] = signal

    for signal in mcp_signals:
        for cluster in clusters.values():
            if _matches_mcp_coverage(signal, cluster):
                cluster.coverage[signal.id] = signal

    candidates = [_candidate_from_cluster(cluster) for cluster in clusters.values()]
    candidates = [
        candidate
        for candidate in candidates
        if candidate.score >= min_score and _matches_domain(candidate, domain_filter)
    ]
    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            candidate.existing_mcp_coverage,
            candidate.provider.casefold(),
            candidate.api_name.casefold(),
        )
    )
    ranked = [replace(candidate, rank=rank) for rank, candidate in enumerate(candidates, start=1)]

    return OpenAPIMCPCandidateReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        domain=domain_filter,
        min_score=round(min_score, 1),
        total_candidates=len(ranked),
        candidates=ranked,
    )


def _candidate_from_cluster(cluster: _Cluster) -> OpenAPIMCPCandidate:
    signals = sorted(cluster.signals.values(), key=lambda signal: signal.id)
    coverage = sorted(cluster.coverage.values(), key=lambda signal: signal.id)
    adapter_counts = Counter(signal.source_adapter for signal in signals)
    evidence_count = len(signals)
    demand_hits = _demand_hits(signals)
    avg_credibility = sum(signal.credibility for signal in signals) / evidence_count
    complexity = _implementation_complexity(signals)
    covered = bool(coverage)

    evidence_score = min(evidence_count / 4, 1.0) * 100
    demand_score = min(demand_hits / 4, 1.0) * 100
    credibility_score = avg_credibility * 100
    complexity_score = {"low": 100.0, "medium": 65.0, "high": 35.0}[complexity]
    coverage_score = 20.0 if covered else 100.0

    components = [
        OpenAPIMCPCandidateScoreComponent(
            name="evidence",
            score=round(evidence_score, 1),
            weight=0.25,
            explanation=f"{evidence_count} corroborating API/demand signals.",
        ),
        OpenAPIMCPCandidateScoreComponent(
            name="demand",
            score=round(demand_score, 1),
            weight=0.20,
            explanation=f"{demand_hits} demand keyword hits across evidence text.",
        ),
        OpenAPIMCPCandidateScoreComponent(
            name="credibility",
            score=round(credibility_score, 1),
            weight=0.20,
            explanation=f"Average source credibility is {avg_credibility:.2f}.",
        ),
        OpenAPIMCPCandidateScoreComponent(
            name="implementation_complexity",
            score=round(complexity_score, 1),
            weight=0.15,
            explanation=f"Implementation complexity classified as {complexity}.",
        ),
        OpenAPIMCPCandidateScoreComponent(
            name="mcp_coverage_gap",
            score=round(coverage_score, 1),
            weight=0.20,
            explanation=(
                f"{len(coverage)} matching MCP coverage signals found."
                if covered
                else "No matching MCP coverage signals found."
            ),
        ),
    ]
    score = round(sum(component.score * component.weight for component in components), 1)

    return OpenAPIMCPCandidate(
        provider=cluster.provider,
        api_name=cluster.api_name,
        domain=cluster.domain,
        score=score,
        rank=0,
        existing_mcp_coverage=covered,
        coverage_signal_ids=[signal.id for signal in coverage],
        evidence_signal_ids=[signal.id for signal in signals],
        source_adapters=dict(sorted(adapter_counts.items())),
        score_components=components,
        implementation_complexity=complexity,
        explanation=(
            f"{cluster.provider} {cluster.api_name} has {evidence_count} evidence signals"
            f" from {len(adapter_counts)} adapters; "
            f"{'existing MCP coverage lowers priority' if covered else 'no MCP coverage detected'}."
        ),
    )


def _is_openapi_signal(signal: Signal) -> bool:
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    text = _signal_text(signal)
    if signal.source_adapter == "apis_guru":
        return True
    if signal.source_adapter in OPENAPI_SOURCE_ADAPTERS and (
        "openapi" in text or "swagger" in text or "api_name" in metadata
    ):
        return True
    return bool(metadata.get("swagger_url") or metadata.get("openapi_url") or metadata.get("api_name"))


def _is_candidate_seed_signal(signal: Signal) -> bool:
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    return signal.source_adapter == "apis_guru" or bool(
        metadata.get("provider")
        or metadata.get("api_name")
        or metadata.get("swagger_url")
        or metadata.get("openapi_url")
    )


def _is_mcp_signal(signal: Signal) -> bool:
    text = _signal_text(signal)
    return signal.source_adapter in MCP_COVERAGE_ADAPTERS and (
        "mcp" in text or "model context protocol" in text or signal.source_adapter == "mcp_registry"
    )


def _provider(signal: Signal) -> str:
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    value = metadata.get("provider") or metadata.get("x-providerName") or metadata.get("owner")
    return _clean_name(value) or _clean_name(signal.author) or _title_provider(signal.title)


def _api_name(signal: Signal) -> str:
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    value = metadata.get("api_name") or metadata.get("x-serviceName") or metadata.get("service")
    return _clean_name(value) or _clean_title(signal.title)


def _domain(signal: Signal, provider: str) -> str:
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    for key in ("domain", "category"):
        value = _clean_name(metadata.get(key))
        if value:
            return value.casefold()
    categories = metadata.get("categories")
    if isinstance(categories, list):
        for category in categories:
            value = _clean_name(category)
            if value and value.casefold() != provider.casefold():
                return value.casefold()
    for tag in signal.tags:
        if tag.casefold() != provider.casefold():
            return tag.casefold()
    return "unknown"


def _matches_cluster(signal: Signal, cluster: _Cluster) -> bool:
    text = _signal_text(signal)
    provider = cluster.provider.casefold()
    api_name = cluster.api_name.casefold()
    tokens = _cluster_tokens(cluster)
    if provider and provider in text:
        return True
    if api_name and api_name in text:
        return True
    return bool(tokens and sum(1 for token in tokens if token in text) >= min(2, len(tokens)))


def _matches_mcp_coverage(signal: Signal, cluster: _Cluster) -> bool:
    text = _signal_text(signal)
    provider = cluster.provider.casefold()
    if provider and provider in text:
        return True
    provider_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", provider)
        if len(token) >= 3 and token not in _GENERIC_TOKENS
    }
    return bool(provider_tokens and all(token in text for token in provider_tokens))


def _matches_domain(candidate: OpenAPIMCPCandidate, domain: str | None) -> bool:
    if not domain:
        return True
    haystack = " ".join(
        [
            candidate.domain,
            candidate.provider,
            candidate.api_name,
            " ".join(candidate.source_adapters),
        ]
    ).casefold()
    return domain in haystack


def _demand_hits(signals: list[Signal]) -> int:
    text = " ".join(_signal_text(signal) for signal in signals)
    return sum(1 for keyword in _DEMAND_KEYWORDS if keyword in text)


def _implementation_complexity(signals: list[Signal]) -> str:
    text = " ".join(_signal_text(signal) for signal in signals)
    high_hits = sum(1 for keyword in _COMPLEXITY_HIGH_KEYWORDS if keyword in text)
    has_openapi_spec = any(
        bool(signal.metadata.get("swagger_url") or signal.metadata.get("openapi_ver"))
        for signal in signals
        if isinstance(signal.metadata, dict)
    )
    if high_hits >= 3:
        return "high"
    if has_openapi_spec and high_hits == 0:
        return "low"
    return "medium"


def _cluster_tokens(cluster: _Cluster) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", f"{cluster.provider} {cluster.api_name}".casefold())
        if len(token) >= 3 and token not in _GENERIC_TOKENS
    }


def _signal_text(signal: Signal) -> str:
    metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
    chunks = [
        signal.title,
        signal.content,
        signal.url,
        " ".join(signal.tags),
        json.dumps(metadata, sort_keys=True),
    ]
    return " ".join(str(chunk) for chunk in chunks if chunk).casefold()


def _cluster_key(provider: str, api_name: str) -> str:
    return f"{_key_part(provider)}::{_key_part(api_name)}"


def _key_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _clean_name(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _clean_title(value: str) -> str:
    title = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
    title = re.sub(r"\b(openapi|swagger|api)\b", "", title, flags=re.IGNORECASE).strip(" -:")
    return title or value.strip()


def _title_provider(title: str) -> str:
    cleaned = _clean_title(title)
    parts = re.split(r"[:/|-]", cleaned, maxsplit=1)
    return parts[0].strip() if parts and parts[0].strip() else cleaned


def _normalize_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None
