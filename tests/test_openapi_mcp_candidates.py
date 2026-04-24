from __future__ import annotations

import pytest

from max.analysis.openapi_mcp_candidates import build_openapi_mcp_candidate_report
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "openapi_mcp_candidates.db"
    store = Store(db_path=str(db_path), wal_mode=True)
    try:
        yield store
    finally:
        store.close()


def _signal(
    signal_id: str,
    *,
    adapter: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    credibility: float = 0.7,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter,
        title=title,
        content=content,
        url=f"https://example.com/{signal_id}",
        tags=tags or [],
        credibility=credibility,
        metadata=metadata or {},
    )


def _seed_candidates(store: Store) -> None:
    store.insert_signal(
        _signal(
            "sig-stripe-openapi",
            adapter="apis_guru",
            title="Stripe API (2025-01-01)",
            content="Payments API with OpenAPI description for developers and integrations.",
            tags=["stripe", "financial"],
            credibility=0.9,
            metadata={
                "provider": "Stripe",
                "api_name": "Payments",
                "swagger_url": "https://example.com/stripe/openapi.json",
                "openapi_ver": "3.1.0",
                "categories": ["financial"],
            },
        )
    )
    store.insert_signal(
        _signal(
            "sig-stripe-github",
            adapter="github",
            title="Stripe Payments OpenAPI client",
            content="Developers request agent workflow automation and SDK integration support.",
            tags=["stripe", "openapi"],
            credibility=0.8,
        )
    )
    store.insert_signal(
        _signal(
            "sig-slack-openapi",
            adapter="apis_guru",
            title="Slack Web API",
            content="Collaboration API for workflow automation, apps, and developer integrations.",
            tags=["collaboration"],
            credibility=0.85,
            metadata={
                "provider": "Slack",
                "api_name": "Web API",
                "swagger_url": "https://example.com/slack/openapi.json",
                "openapi_ver": "3.0.0",
                "categories": ["collaboration"],
            },
        )
    )
    store.insert_signal(
        _signal(
            "sig-slack-mcp",
            adapter="mcp_registry",
            title="Slack MCP server",
            content="MCP server for Slack Web API messaging and workspace tools.",
            tags=["mcp", "slack"],
            credibility=0.9,
            metadata={"server_name": "slack-mcp", "categories": ["collaboration"]},
        )
    )
    store.insert_signal(
        _signal(
            "sig-twilio-openapi",
            adapter="apis_guru",
            title="Twilio Messaging API",
            content="Messaging API with OpenAPI for SMS integrations.",
            tags=["communications"],
            credibility=0.65,
            metadata={
                "provider": "Twilio",
                "api_name": "Messaging",
                "swagger_url": "https://example.com/twilio/openapi.json",
                "categories": ["communications"],
            },
        )
    )


def test_ranks_uncovered_openapi_candidates_and_includes_evidence_breakdowns(store: Store) -> None:
    _seed_candidates(store)

    report = build_openapi_mcp_candidate_report(store)

    by_provider = {candidate.provider: candidate for candidate in report.candidates}
    assert report.total_candidates == 3
    assert report.candidates[0].provider == "Stripe"
    assert by_provider["Stripe"].existing_mcp_coverage is False
    assert by_provider["Stripe"].evidence_signal_ids == ["sig-stripe-github", "sig-stripe-openapi"]
    assert by_provider["Stripe"].source_adapters == {"apis_guru": 1, "github": 1}
    assert {component.name for component in by_provider["Stripe"].score_components} == {
        "evidence",
        "demand",
        "credibility",
        "implementation_complexity",
        "mcp_coverage_gap",
    }
    assert by_provider["Stripe"].explanation


def test_existing_mcp_coverage_lowers_candidate_priority(store: Store) -> None:
    _seed_candidates(store)

    report = build_openapi_mcp_candidate_report(store)
    by_provider = {candidate.provider: candidate for candidate in report.candidates}

    assert by_provider["Slack"].existing_mcp_coverage is True
    assert by_provider["Slack"].coverage_signal_ids == ["sig-slack-mcp"]
    assert by_provider["Slack"].score < by_provider["Stripe"].score


def test_domain_and_minimum_score_filters_are_deterministic(store: Store) -> None:
    _seed_candidates(store)

    financial = build_openapi_mcp_candidate_report(store, domain="financial")
    assert [candidate.provider for candidate in financial.candidates] == ["Stripe"]
    assert financial.domain == "financial"

    high_score = build_openapi_mcp_candidate_report(store, min_score=70.0)
    assert all(candidate.score >= 70.0 for candidate in high_score.candidates)
    assert [candidate.provider for candidate in high_score.candidates] == ["Stripe"]


def test_invalid_minimum_score_raises(store: Store) -> None:
    with pytest.raises(ValueError):
        build_openapi_mcp_candidate_report(store, min_score=-0.1)
