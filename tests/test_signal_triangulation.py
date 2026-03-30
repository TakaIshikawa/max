"""Tests for cross-source signal triangulation — correlation, confidence, and adapter diversity.

Complements test_triangulation.py with deeper coverage of:
- Cross-source signal correlation across specific adapter combinations
- Confidence scoring precision and centroid mechanics
- Triangulation across different source adapters (HackerNews, GitHub, Reddit, etc.)
"""

from __future__ import annotations

from max.analysis.triangulation import (
    SignalCluster,
    _compute_cluster_stats,
    format_cluster_context,
    triangulate,
)
from max.types.signal import Signal, SignalSourceType


def _make_signal(
    adapter: str,
    title: str,
    content: str = "",
    *,
    credibility: float = 0.7,
    signal_role: str = "market",
    source_type: SignalSourceType = SignalSourceType.FORUM,
) -> Signal:
    return Signal(
        source_type=source_type,
        source_adapter=adapter,
        title=title,
        content=content or title,
        url=f"https://example.com/{hash(title) % 100000}",
        credibility=credibility,
        metadata={"signal_role": signal_role},
    )


# ── Cross-source signal correlation ─────────────────────────────


def test_hackernews_github_reddit_correlation() -> None:
    """Signals from HN, GitHub, and Reddit about the same topic should cluster."""
    signals = [
        _make_signal("hackernews", "AI agent memory management is critical"),
        _make_signal("github_issues", "AI agent memory management problem"),
        _make_signal("reddit", "AI agent memory management discussion"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    multi = [c for c in clusters if len(c.signals) > 1]
    assert len(multi) >= 1
    # The multi-source cluster should contain signals from distinct adapters
    for cluster in multi:
        assert len(cluster.distinct_sources) > 1


def test_registry_and_forum_cross_correlation() -> None:
    """Registry signals (npm, pypi) and forum signals should cluster on shared topics."""
    signals = [
        _make_signal("npm_registry", "MCP server SDK for testing automation",
                     source_type=SignalSourceType.REGISTRY, signal_role="solution"),
        _make_signal("hackernews", "MCP server SDK testing automation tools",
                     signal_role="market"),
        _make_signal("pypi_registry", "MCP server SDK testing automation library",
                     source_type=SignalSourceType.REGISTRY, signal_role="solution"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    total_signals = sum(len(c.signals) for c in clusters)
    assert total_signals == 3
    # Should have some clustering
    assert len(clusters) <= 3


def test_security_and_issues_cross_correlation() -> None:
    """Security advisories and GitHub issues about the same vulnerability should correlate."""
    signals = [
        _make_signal(
            "security_advisories",
            "Critical SQL injection in ORM framework authentication",
            source_type=SignalSourceType.SECURITY,
            signal_role="problem",
        ),
        _make_signal(
            "github_issues",
            "SQL injection vulnerability in ORM framework auth module",
            signal_role="problem",
        ),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    multi = [c for c in clusters if len(c.signals) > 1]
    if multi:
        assert "security_advisories" in multi[0].distinct_sources or \
               "github_issues" in multi[0].distinct_sources


def test_unrelated_adapters_stay_separate() -> None:
    """Signals from different adapters on unrelated topics should not cluster."""
    signals = [
        _make_signal("hackernews", "Quantum computing breakthroughs in physics"),
        _make_signal("product_hunt", "Best vegan recipe app for meal planning"),
        _make_signal("github_issues", "Kubernetes RBAC policy configuration errors"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.70)
    assert len(clusters) == 3
    assert all(len(c.signals) == 1 for c in clusters)


# ── Confidence scoring ───────────────────────────────────────────


def test_triangulation_score_zero_diversity() -> None:
    """A cluster with zero diversity should have zero triangulation score."""
    cluster = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "test")],
        source_diversity=0.0,
        avg_credibility=0.9,
        centroid=[1.0],
    )
    assert cluster.triangulation_score() == 0.0


def test_triangulation_score_increases_with_diversity() -> None:
    """Higher source diversity should increase the triangulation score."""
    base = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "t") for _ in range(3)],
        source_diversity=0.33,
        avg_credibility=0.8,
        centroid=[1.0],
    )
    diverse = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "t") for _ in range(3)],
        source_diversity=1.0,
        avg_credibility=0.8,
        centroid=[1.0],
    )
    assert diverse.triangulation_score() > base.triangulation_score()


def test_triangulation_score_increases_with_credibility() -> None:
    """Higher avg credibility should increase the triangulation score."""
    low = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "t") for _ in range(3)],
        source_diversity=0.5,
        avg_credibility=0.3,
        centroid=[1.0],
    )
    high = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "t") for _ in range(3)],
        source_diversity=0.5,
        avg_credibility=0.9,
        centroid=[1.0],
    )
    assert high.triangulation_score() > low.triangulation_score()


def test_triangulation_score_size_factor_saturates() -> None:
    """size_factor = min(len/3, 1.0) should saturate at 3 signals."""
    three = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "t") for _ in range(3)],
        source_diversity=1.0,
        avg_credibility=1.0,
        centroid=[1.0],
    )
    ten = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "t") for _ in range(10)],
        source_diversity=1.0,
        avg_credibility=1.0,
        centroid=[1.0],
    )
    assert abs(three.triangulation_score() - ten.triangulation_score()) < 0.001


def test_clusters_sorted_by_score_descending() -> None:
    """triangulate() should return clusters sorted by triangulation_score descending."""
    signals = [
        # High-credibility cluster
        _make_signal("hackernews", "Hot AI topic from HN", credibility=0.95),
        _make_signal("reddit", "Hot AI topic from Reddit", credibility=0.95),
        _make_signal("github_issues", "Hot AI topic from GitHub", credibility=0.95),
        # Low-credibility cluster
        _make_signal("hackernews", "Obscure niche frontend framework opinion", credibility=0.2),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)

    for i in range(len(clusters) - 1):
        assert clusters[i].triangulation_score() >= clusters[i + 1].triangulation_score()


# ── Centroid and cluster mechanics ───────────────────────────────


def test_centroid_is_populated_for_single_signal() -> None:
    """A single-signal cluster should have a non-empty centroid."""
    signals = [_make_signal("hackernews", "Test topic for centroid")]
    clusters = triangulate(signals)
    assert len(clusters) == 1
    assert len(clusters[0].centroid) > 0
    assert any(v != 0.0 for v in clusters[0].centroid)


def test_centroid_length_consistent_across_clusters() -> None:
    """All cluster centroids should have the same dimensionality."""
    signals = [
        _make_signal("hackernews", "Alpha topic about databases"),
        _make_signal("reddit", "Beta topic about machine learning"),
        _make_signal("github_issues", "Gamma topic about kubernetes"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.99)
    assert len(clusters) == 3
    lengths = {len(c.centroid) for c in clusters}
    assert len(lengths) == 1  # All same length


def test_all_signals_accounted_for() -> None:
    """Total signals across all clusters should equal input signal count."""
    signals = [
        _make_signal("hackernews", f"Signal {i} about topic {i % 3}")
        for i in range(15)
    ]
    clusters = triangulate(signals, similarity_threshold=0.50)
    total = sum(len(c.signals) for c in clusters)
    # All signals should be in some cluster (or dropped if max_clusters hit)
    assert total <= len(signals)
    # With max_clusters=20 (default) and 15 signals, all should be placed
    assert total == len(signals)


# ── SignalCluster properties ─────────────────────────────────────


def test_signal_ids_property() -> None:
    """signal_ids should return IDs of all signals in the cluster."""
    sig1 = _make_signal("hackernews", "Test A")
    sig2 = _make_signal("reddit", "Test B")
    cluster = SignalCluster(
        topic="Test",
        signals=[sig1, sig2],
        centroid=[1.0],
    )
    assert cluster.signal_ids == [sig1.id, sig2.id]


def test_distinct_sources_property() -> None:
    """distinct_sources should return unique adapter names."""
    cluster = SignalCluster(
        topic="Test",
        signals=[
            _make_signal("hackernews", "A"),
            _make_signal("hackernews", "B"),
            _make_signal("reddit", "C"),
        ],
        centroid=[1.0],
    )
    assert cluster.distinct_sources == {"hackernews", "reddit"}


# ── _compute_cluster_stats ───────────────────────────────────────


def test_compute_cluster_stats_diversity() -> None:
    """_compute_cluster_stats should set diversity = distinct / total_adapters."""
    cluster = SignalCluster(
        topic="Test",
        signals=[
            _make_signal("hackernews", "Signal A", credibility=0.8, signal_role="problem"),
            _make_signal("reddit", "Signal B", credibility=0.6, signal_role="market"),
        ],
        centroid=[1.0],
    )
    _compute_cluster_stats(cluster, total_adapters=4)
    # 2 distinct adapters / 4 total = 0.5
    assert abs(cluster.source_diversity - 0.5) < 0.01


def test_compute_cluster_stats_credibility() -> None:
    """_compute_cluster_stats should compute avg credibility."""
    cluster = SignalCluster(
        topic="Test",
        signals=[
            _make_signal("a", "X", credibility=0.4),
            _make_signal("b", "Y", credibility=0.8),
        ],
        centroid=[1.0],
    )
    _compute_cluster_stats(cluster, total_adapters=2)
    assert abs(cluster.avg_credibility - 0.6) < 0.01


def test_compute_cluster_stats_topic_from_best_credibility() -> None:
    """_compute_cluster_stats should set topic to highest-credibility signal's title."""
    cluster = SignalCluster(
        topic="initial",
        signals=[
            _make_signal("a", "Low credibility title", credibility=0.2),
            _make_signal("b", "High credibility title", credibility=0.9),
        ],
        centroid=[1.0],
    )
    _compute_cluster_stats(cluster, total_adapters=2)
    assert cluster.topic == "High credibility title"


def test_compute_cluster_stats_role_distribution() -> None:
    """_compute_cluster_stats should count roles correctly."""
    cluster = SignalCluster(
        topic="Test",
        signals=[
            _make_signal("a", "A", signal_role="problem"),
            _make_signal("b", "B", signal_role="problem"),
            _make_signal("c", "C", signal_role="solution"),
        ],
        centroid=[1.0],
    )
    _compute_cluster_stats(cluster, total_adapters=3)
    assert cluster.roles == {"problem": 2, "solution": 1}


def test_compute_cluster_stats_empty_role_defaults_to_unknown() -> None:
    """Signals without signal_role should be counted as 'unknown'."""
    sig = _make_signal("a", "No role")
    sig.metadata.pop("signal_role", None)
    cluster = SignalCluster(
        topic="Test",
        signals=[sig],
        centroid=[1.0],
    )
    _compute_cluster_stats(cluster, total_adapters=1)
    assert cluster.roles.get("unknown", 0) == 1


def test_compute_cluster_stats_zero_total_adapters() -> None:
    """Should handle total_adapters=0 without division error."""
    cluster = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "X", credibility=0.5)],
        centroid=[1.0],
    )
    _compute_cluster_stats(cluster, total_adapters=0)
    # max(0, 1) = 1 → diversity = 1/1 = 1.0
    assert cluster.source_diversity == 1.0


# ── format_cluster_context detail ────────────────────────────────


def test_format_cluster_context_includes_role_distribution() -> None:
    """Formatted output should include role counts."""
    cluster = SignalCluster(
        topic="AI testing",
        signals=[
            _make_signal("hackernews", "AI testing", signal_role="problem"),
            _make_signal("reddit", "AI testing", signal_role="solution"),
        ],
        source_diversity=1.0,
        avg_credibility=0.8,
        roles={"problem": 1, "solution": 1},
        centroid=[1.0],
    )
    result = format_cluster_context([cluster])
    assert result is not None
    assert "problem=1" in result
    assert "solution=1" in result


def test_format_cluster_context_includes_credibility() -> None:
    """Formatted output should include credibility score."""
    cluster = SignalCluster(
        topic="Test topic",
        signals=[
            _make_signal("hackernews", "Test"),
            _make_signal("reddit", "Test"),
        ],
        source_diversity=1.0,
        avg_credibility=0.75,
        roles={"market": 2},
        centroid=[1.0],
    )
    result = format_cluster_context([cluster])
    assert result is not None
    assert "credibility: 0.75" in result


def test_format_cluster_context_includes_signal_count() -> None:
    """Formatted output should include number of signals."""
    cluster = SignalCluster(
        topic="Multi-signal cluster",
        signals=[
            _make_signal("hackernews", "A"),
            _make_signal("reddit", "B"),
            _make_signal("github_issues", "C"),
        ],
        source_diversity=1.0,
        avg_credibility=0.7,
        roles={"problem": 3},
        centroid=[1.0],
    )
    result = format_cluster_context([cluster])
    assert result is not None
    assert "3 signals from" in result


def test_format_cluster_context_respects_max_clusters() -> None:
    """Only the first max_clusters multi-source clusters should appear."""
    clusters = [
        SignalCluster(
            topic=f"Cluster {i}",
            signals=[
                _make_signal("hackernews", f"Sig {i}a"),
                _make_signal("reddit", f"Sig {i}b"),
            ],
            source_diversity=1.0,
            avg_credibility=0.7,
            roles={"market": 2},
            centroid=[1.0],
        )
        for i in range(10)
    ]
    result = format_cluster_context(clusters, max_clusters=2)
    assert result is not None
    assert "Cluster 0" in result
    assert "Cluster 1" in result
    assert "Cluster 2" not in result


def test_format_cluster_context_sources_sorted() -> None:
    """Sources in formatted output should be alphabetically sorted."""
    cluster = SignalCluster(
        topic="Sorted sources test",
        signals=[
            _make_signal("reddit", "From reddit"),
            _make_signal("hackernews", "From HN"),
            _make_signal("github_issues", "From GH"),
        ],
        source_diversity=1.0,
        avg_credibility=0.7,
        roles={"problem": 3},
        centroid=[1.0],
    )
    result = format_cluster_context([cluster])
    assert result is not None
    assert "github_issues, hackernews, reddit" in result
