"""Tests for competitor feature matrix export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.competitor_matrix import (
    SCHEMA_VERSION,
    KIND,
    build_competitor_matrix,
    render_competitor_matrix_json,
    render_competitor_matrix_markdown,
    _collect_competitors,
    _collect_features,
    _build_matrix,
    _categorize_features,
    _analyze_gaps,
    _identify_strengths,
    _extract_feature_keywords,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    solution: str = "Automated testing",
    domain: str = "devtools",
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.solution = solution
    unit.domain = domain
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Signal",
    content: str = "Content",
    tags: list[str] | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=content,
        source_type=SignalSourceType.MARKET,
        source_adapter="test_adapter",
        url="https://example.com",
        tags=tags or [],
    )


def _mock_store(
    units: list | None = None,
    signals: list | None = None,
    prior_art: list | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    store.get_prior_art_matches.return_value = prior_art or []
    return store


# ── Schema and structure tests ───────────────────────────────────────


def test_build_competitor_matrix_schema() -> None:
    store = _mock_store()
    result = build_competitor_matrix(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "competitors" in result
    assert "features" in result
    assert "matrix" in result
    assert "feature_categories" in result
    assert "gap_analysis" in result
    assert "unique_strengths" in result


def test_build_competitor_matrix_domain_filter() -> None:
    store = _mock_store()
    build_competitor_matrix(store, domain="security")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="security")


# ── Competitor collection tests ──────────────────────────────────────


def test_collect_competitors_from_prior_art() -> None:
    units = [_make_unit()]
    store = _mock_store(
        units=units,
        prior_art=[
            {"title": "Tool A", "source": "github", "description": "An analytics dashboard tool"},
            {"title": "Tool B", "source": "npm", "description": "A testing automation framework"},
        ],
    )
    competitors = _collect_competitors(units, store)
    assert len(competitors) == 2
    names = {c["name"] for c in competitors}
    assert "Tool A" in names
    assert "Tool B" in names


def test_collect_competitors_deduplicates() -> None:
    units = [_make_unit(unit_id="bu-1"), _make_unit(unit_id="bu-2")]
    store = MagicMock()
    store.get_prior_art_matches.return_value = [
        {"title": "Same Tool", "source": "github", "description": "A tool"},
    ]
    competitors = _collect_competitors(units, store)
    assert len(competitors) == 1
    assert competitors[0]["mentions"] == 2


def test_collect_competitors_empty() -> None:
    store = _mock_store()
    competitors = _collect_competitors([], store)
    assert competitors == []


# ── Feature collection tests ────────────────────────────────────────


def test_collect_features_from_units() -> None:
    units = [
        _make_unit(solution="Auto deploy"),
        _make_unit(solution="Auto test"),
    ]
    features = _collect_features(units, [])
    assert "Auto deploy" in features
    assert "Auto test" in features


def test_collect_features_from_tags() -> None:
    signals = [
        _make_signal(tags=["python", "docker"]),
        _make_signal(signal_id="sig-2", tags=["python", "kubernetes"]),
    ]
    features = _collect_features([], signals)
    assert "python" in features


def test_collect_features_deduplicates() -> None:
    units = [
        _make_unit(unit_id="bu-1", solution="Same thing"),
        _make_unit(unit_id="bu-2", solution="Same thing"),
    ]
    features = _collect_features(units, [])
    assert features.count("Same thing") == 1


# ── Feature keyword extraction tests ────────────────────────────────


def test_extract_feature_keywords() -> None:
    keywords = _extract_feature_keywords("An api with analytics and monitoring")
    assert "api" in keywords
    assert "analytics" in keywords
    assert "monitoring" in keywords


def test_extract_feature_keywords_empty() -> None:
    keywords = _extract_feature_keywords("No relevant keywords here")
    assert keywords == []


# ── Matrix building tests ────────────────────────────────────────────


def test_build_matrix_structure() -> None:
    competitors = [
        {"name": "A", "features": ["api", "analytics"]},
        {"name": "B", "features": ["api", "monitoring"]},
    ]
    features = ["API access", "Analytics dashboard", "Monitoring"]
    matrix = _build_matrix(competitors, features)
    assert len(matrix) == 3
    for row in matrix:
        assert "feature" in row
        assert "availability" in row
        assert len(row["availability"]) == 2


def test_build_matrix_availability_detection() -> None:
    competitors = [
        {"name": "A", "features": ["api"]},
    ]
    features = ["api endpoint"]
    matrix = _build_matrix(competitors, features)
    assert matrix[0]["availability"][0] == "Yes"


def test_build_matrix_no_match() -> None:
    competitors = [
        {"name": "A", "features": ["api"]},
    ]
    features = ["unrelated feature xyz"]
    matrix = _build_matrix(competitors, features)
    assert matrix[0]["availability"][0] == "—"


# ── Feature categorization tests ────────────────────────────────────


def test_categorize_features() -> None:
    features = ["API endpoint", "Security audit", "Team collaboration"]
    categories = _categorize_features(features)
    cat_names = {c["category"] for c in categories}
    assert "api" in cat_names
    assert "security" in cat_names
    assert "collaboration" in cat_names


def test_categorize_features_fallback_to_core() -> None:
    features = ["Something completely unique"]
    categories = _categorize_features(features)
    core = next(c for c in categories if c["category"] == "core")
    assert "Something completely unique" in core["features"]


# ── Gap analysis tests ───────────────────────────────────────────────


def test_analyze_gaps_identifies_missing_features() -> None:
    matrix = [
        {"feature": "Feature A", "availability": ["—", "—", "—"]},
        {"feature": "Feature B", "availability": ["Yes", "Yes", "Yes"]},
    ]
    competitors = [{"name": "X"}, {"name": "Y"}, {"name": "Z"}]
    gaps = _analyze_gaps(matrix, competitors)
    assert len(gaps) == 1
    assert gaps[0]["feature"] == "Feature A"


def test_analyze_gaps_empty_matrix() -> None:
    gaps = _analyze_gaps([], [])
    assert gaps == []


def test_analyze_gaps_sorted_by_ratio() -> None:
    matrix = [
        {"feature": "A", "availability": ["—", "—", "Yes"]},  # 2/3 gap
        {"feature": "B", "availability": ["—", "—", "—"]},    # 3/3 gap
    ]
    competitors = [{"name": "X"}, {"name": "Y"}, {"name": "Z"}]
    gaps = _analyze_gaps(matrix, competitors)
    assert gaps[0]["feature"] == "B"  # Higher gap ratio first


# ── Strength identification tests ────────────────────────────────────


def test_identify_strengths() -> None:
    matrix = [
        {"feature": "A", "availability": ["Yes", "—"]},
        {"feature": "B", "availability": ["Yes", "Yes"]},
    ]
    competitors = [{"name": "Alpha"}, {"name": "Beta"}]
    strengths = _identify_strengths(matrix, competitors)
    assert len(strengths) == 2
    # Alpha has 100% coverage, Beta has 50%
    assert strengths[0]["competitor"] == "Alpha"
    assert strengths[0]["coverage"] == 1.0


def test_identify_strengths_empty() -> None:
    strengths = _identify_strengths([], [])
    assert strengths == []


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    units = [_make_unit()]
    store = _mock_store(
        units=units,
        signals=[_make_signal(tags=["python"])],
        prior_art=[{"title": "Comp A", "source": "github", "description": "An api tool"}],
    )
    report = build_competitor_matrix(store)
    md = render_competitor_matrix_markdown(report)

    assert "# Competitor Feature Matrix" in md
    assert "## Feature Comparison" in md
    assert "## Feature Categories" in md
    assert "## Competitive Gaps" in md
    assert "## Unique Strengths" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_competitor_matrix(store)
    md = render_competitor_matrix_markdown(report)
    assert "# Competitor Feature Matrix" in md


def test_render_markdown_no_competitors() -> None:
    store = _mock_store()
    report = build_competitor_matrix(store)
    md = render_competitor_matrix_markdown(report)
    assert "No competitor data available" in md


def test_render_json_valid() -> None:
    store = _mock_store()
    report = build_competitor_matrix(store)
    parsed = json.loads(render_competitor_matrix_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_json_roundtrip() -> None:
    units = [_make_unit()]
    store = _mock_store(
        units=units,
        signals=[_make_signal()],
        prior_art=[{"title": "Tool X", "source": "npm", "description": "analytics dashboard"}],
    )
    report = build_competitor_matrix(store)
    parsed = json.loads(render_competitor_matrix_json(report))
    assert len(parsed["competitors"]) >= 1
    assert len(parsed["matrix"]) >= 1
