"""Tests for technology adoption lifecycle analysis."""

from __future__ import annotations

import json

from max.analysis import (
    AdoptionStage,
    build_adoption_profile,
    classify_adoption_stage,
    render_adoption_profile_json,
    render_adoption_profile_markdown,
)


def _signal(
    title: str,
    *,
    source: str = "github",
    published_at: str = "2026-01-01T00:00:00+00:00",
    community_size: int | None = None,
    enterprise_mentions: int | None = None,
) -> dict:
    signal = {
        "title": title,
        "content": title,
        "source_type": source,
        "published_at": published_at,
    }
    if community_size is not None:
        signal["community_size"] = community_size
    if enterprise_mentions is not None:
        signal["enterprise_mentions"] = enterprise_mentions
    return signal


def test_classifies_innovators_from_sparse_experimental_signals() -> None:
    signals = [
        _signal("Prototype alpha experiment from research team"),
        _signal("Proof of concept preview at hackathon", source="blog"),
    ]

    classification = classify_adoption_stage(signals)

    assert classification.stage == AdoptionStage.INNOVATORS
    assert classification.signal_count == 2
    assert "Experimental usage language" in classification.indicators


def test_classifies_early_adopters_from_growth_and_docs() -> None:
    signals = [
        _signal("Beta launch with quickstart docs and community adoption", community_size=800),
        _signal("Pilot case study includes tutorial guide", source="blog"),
        _signal("Developers discuss growing SDK adoption", source="forum"),
    ]

    classification = classify_adoption_stage(signals)

    assert classification.stage == AdoptionStage.EARLY_ADOPTERS
    assert classification.confidence > 0.45
    assert "Mature documentation" in classification.indicators


def test_classifies_early_majority_from_enterprise_and_mature_docs() -> None:
    signals = [
        _signal("Production guide and API reference for enterprise SSO", community_size=15_000),
        _signal("Security review confirms SOC 2 compliance", source="security"),
        _signal("Customer case study shows mainstream adoption", source="analyst"),
        _signal("SDK documentation and tutorial published", source="docs"),
    ]

    classification = classify_adoption_stage(signals)

    assert classification.stage == AdoptionStage.EARLY_MAJORITY
    assert "Repeated enterprise mentions" in classification.indicators
    assert "Large community" in classification.indicators


def test_classifies_late_majority_from_broad_enterprise_standardization() -> None:
    signals = [
        _signal("Enterprise standard with governance and procurement support", source="analyst", community_size=75_000),
        _signal("Best practice guide for production compliance", source="docs"),
        _signal("SLA and SSO documentation for mature deployments", source="vendor"),
        _signal("Mainstream adoption case study", source="news"),
        _signal("Security review and tutorial published", source="security"),
        _signal("Community guide documents widely used workflows", source="forum"),
    ]

    classification = classify_adoption_stage(signals)

    assert classification.stage == AdoptionStage.LATE_MAJORITY
    assert classification.confidence >= 0.65


def test_classifies_laggards_from_legacy_replacement_signals() -> None:
    signals = [
        _signal("Legacy platform enters maintenance mode and migration planning", source="vendor", community_size=80_000),
        _signal("Deprecated API sunset announced as replacement becomes standard", source="docs"),
        _signal("Enterprise procurement blocks end of life dependency", source="analyst"),
        _signal("Production guide focuses on migration from legacy systems", source="security"),
        _signal("Widely used mature standard now has replacement roadmap", source="news"),
    ]

    classification = classify_adoption_stage(signals)

    assert classification.stage == AdoptionStage.LAGGARDS
    assert "Legacy or replacement language" in classification.indicators


def test_profile_detects_ascending_trajectory() -> None:
    signals = [
        _signal("Prototype alpha experiment", published_at="2026-01-01T00:00:00+00:00"),
        _signal("Preview research proof of concept", source="blog", published_at="2026-01-03T00:00:00+00:00"),
        _signal("Production guide with enterprise SSO and docs", source="docs", published_at="2026-03-01T00:00:00+00:00", community_size=20_000),
        _signal("Security review and mainstream case study", source="analyst", published_at="2026-03-05T00:00:00+00:00"),
    ]

    profile = build_adoption_profile("agent platforms", signals)

    assert profile.topic == "agent platforms"
    assert profile.trajectory == "ascending"
    assert profile.dominant_stage == AdoptionStage.EARLY_MAJORITY
    assert len(profile.classifications) == 3


def test_profile_detects_declining_trajectory() -> None:
    signals = [
        _signal("Enterprise production standard with governance docs", source="analyst", published_at="2026-01-01T00:00:00+00:00", community_size=30_000),
        _signal("SOC 2 compliance and procurement guide", source="docs", published_at="2026-01-02T00:00:00+00:00"),
        _signal("Prototype replacement experiment", source="github", published_at="2026-04-01T00:00:00+00:00"),
        _signal("Alpha research preview", source="blog", published_at="2026-04-02T00:00:00+00:00"),
    ]

    profile = build_adoption_profile("workflow engines", signals)

    assert profile.trajectory == "declining"


def test_markdown_and_json_renderers_produce_valid_output() -> None:
    profile = build_adoption_profile(
        "runtime tooling",
        [
            _signal("Beta launch with quickstart docs", community_size=500),
            _signal("Pilot case study and growing community", source="blog"),
            _signal("SDK tutorial for developers", source="docs"),
        ],
    )

    markdown = render_adoption_profile_markdown(profile)
    rendered_json = render_adoption_profile_json(profile)
    payload = json.loads(rendered_json)

    assert "# Adoption Lifecycle Profile: runtime tooling" in markdown
    assert "| Segment | Stage | Confidence | Signals | Indicators |" in markdown
    assert payload["topic"] == "runtime tooling"
    assert payload["dominant_stage"] == profile.dominant_stage.value
    assert payload["classifications"][-1]["stage"] == profile.dominant_stage.value


def test_empty_profile_is_stable_with_zero_confidence() -> None:
    profile = build_adoption_profile("empty topic", [])

    assert profile.dominant_stage == AdoptionStage.INNOVATORS
    assert profile.trajectory == "stable"
    assert profile.classifications[0].confidence == 0.0
