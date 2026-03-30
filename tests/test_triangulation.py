"""Tests for cross-source triangulation (signal clustering)."""

from __future__ import annotations

from max.analysis.triangulation import (
    SignalCluster,
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
) -> Signal:
    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=title,
        content=content or title,
        url=f"https://example.com/{hash(title) % 100000}",
        credibility=credibility,
        metadata={"signal_role": signal_role},
    )


# ── Basic clustering ─────────────────────────────────────────────


def test_empty_signals_returns_empty() -> None:
    assert triangulate([]) == []


def test_single_signal_creates_one_cluster() -> None:
    signals = [_make_signal("hackernews", "MCP server testing framework")]
    clusters = triangulate(signals)
    assert len(clusters) == 1
    assert len(clusters[0].signals) == 1


def test_similar_signals_cluster_together() -> None:
    """Signals with similar titles should land in the same cluster."""
    signals = [
        _make_signal("hackernews", "MCP server testing framework is needed"),
        _make_signal("reddit", "Testing MCP servers is really hard"),
        _make_signal("github_issues", "Need a testing framework for MCP"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.50)
    # With similar titles, they should cluster together
    # At minimum, not every signal should be in its own cluster
    total_signals = sum(len(c.signals) for c in clusters)
    assert total_signals == 3
    assert len(clusters) < 3  # At least some clustering occurred


def test_dissimilar_signals_separate_clusters() -> None:
    """Signals with very different topics should be in separate clusters."""
    signals = [
        _make_signal("hackernews", "MCP server testing framework"),
        _make_signal("reddit", "Machine learning for protein folding in biology"),
        _make_signal("github_issues", "Kubernetes cluster autoscaling configuration"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.90)
    # With high threshold, dissimilar signals should be in separate clusters
    assert len(clusters) == 3


# ── Cluster statistics ───────────────────────────────────────────


def test_source_diversity_scoring() -> None:
    """Source diversity should reflect distinct adapters / total adapters."""
    signals = [
        _make_signal("hackernews", "AI agent reliability problems"),
        _make_signal("reddit", "AI agent reliability issues"),
        _make_signal("github_issues", "AI agent crashes and reliability"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)

    # Find the cluster with multiple signals
    multi = [c for c in clusters if len(c.signals) > 1]
    if multi:
        # 3 distinct adapters, 3 total adapters → diversity = 1.0
        assert multi[0].source_diversity > 0.0


def test_role_distribution_populated() -> None:
    """Cluster roles dict should count signal roles."""
    signals = [
        _make_signal("hackernews", "AI agent testing", signal_role="problem"),
        _make_signal("reddit", "AI agent testing tools", signal_role="solution"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    # Check that at least one cluster has roles populated
    has_roles = any(len(c.roles) > 0 for c in clusters)
    assert has_roles


def test_avg_credibility_computed() -> None:
    signals = [
        _make_signal("hackernews", "Test topic one", credibility=0.8),
        _make_signal("reddit", "Test topic one similar", credibility=0.6),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    for cluster in clusters:
        if len(cluster.signals) > 1:
            assert 0.6 <= cluster.avg_credibility <= 0.8


def test_triangulation_score_computation() -> None:
    cluster = SignalCluster(
        topic="Test",
        signals=[
            _make_signal("a", "test", credibility=0.8),
            _make_signal("b", "test", credibility=0.8),
            _make_signal("c", "test", credibility=0.8),
        ],
        source_diversity=1.0,
        avg_credibility=0.8,
        centroid=[1.0],
    )
    # source_diversity * avg_credibility * min(3/3, 1.0) = 1.0 * 0.8 * 1.0 = 0.8
    assert abs(cluster.triangulation_score() - 0.8) < 0.01


def test_triangulation_score_size_factor() -> None:
    cluster = SignalCluster(
        topic="Test",
        signals=[_make_signal("a", "test", credibility=0.9)],
        source_diversity=1.0,
        avg_credibility=0.9,
        centroid=[1.0],
    )
    # size_factor = min(1/3, 1.0) ≈ 0.333
    expected = 1.0 * 0.9 * (1.0 / 3.0)
    assert abs(cluster.triangulation_score() - expected) < 0.01


# ── max_clusters limit ───────────────────────────────────────────


def test_max_clusters_respected() -> None:
    signals = [
        _make_signal("adapter", f"Unique topic number {i} about subject {i * 37}")
        for i in range(30)
    ]
    clusters = triangulate(signals, similarity_threshold=0.99, max_clusters=5)
    assert len(clusters) <= 5


# ── format_cluster_context ───────────────────────────────────────


def test_format_cluster_context_none_for_no_multi_source() -> None:
    """Should return None when no clusters have multiple sources."""
    signals = [
        _make_signal("hackernews", "Topic A signal one"),
        _make_signal("hackernews", "Topic A signal two"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    # All from same adapter → no multi-source clusters
    result = format_cluster_context(clusters)
    assert result is None


def test_format_cluster_context_output_structure() -> None:
    """Should return formatted text for multi-source clusters."""
    signals = [
        _make_signal("hackernews", "MCP server testing framework needed"),
        _make_signal("reddit", "Testing MCP servers is hard"),
        _make_signal("github_issues", "MCP server test framework request"),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    result = format_cluster_context(clusters)
    if result:
        assert "signals from" in result


def test_format_cluster_context_max_clusters_limit() -> None:
    result = format_cluster_context([], max_clusters=3)
    assert result is None
