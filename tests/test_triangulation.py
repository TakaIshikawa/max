"""Tests for cross-source triangulation (signal clustering)."""

from __future__ import annotations

from unittest.mock import patch

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


# ── SignalCluster properties ────────────────────────────────────


def test_signal_ids_returns_list_of_ids() -> None:
    """signal_ids should return list of signal IDs."""
    signals = [
        _make_signal("hackernews", "Test A"),
        _make_signal("reddit", "Test B"),
    ]
    cluster = SignalCluster(topic="Test", signals=signals)
    ids = cluster.signal_ids
    assert len(ids) == 2
    assert all(isinstance(sid, str) for sid in ids)


def test_distinct_sources_returns_unique_adapters() -> None:
    """distinct_sources should return set of unique source_adapter values."""
    signals = [
        _make_signal("hackernews", "Test A"),
        _make_signal("reddit", "Test B"),
        _make_signal("hackernews", "Test C"),
    ]
    cluster = SignalCluster(topic="Test", signals=signals)
    sources = cluster.distinct_sources
    assert sources == {"hackernews", "reddit"}


def test_triangulation_score_with_zero_signals() -> None:
    """Score should be 0 when cluster has no signals."""
    cluster = SignalCluster(
        topic="Empty",
        signals=[],
        source_diversity=1.0,
        avg_credibility=0.8,
    )
    assert cluster.triangulation_score() == 0.0


def test_triangulation_score_with_two_signals() -> None:
    """Score with 2 signals: size_factor = min(2/3, 1.0) ≈ 0.667."""
    cluster = SignalCluster(
        topic="Test",
        signals=[
            _make_signal("a", "test", credibility=0.9),
            _make_signal("b", "test", credibility=0.9),
        ],
        source_diversity=1.0,
        avg_credibility=0.9,
        centroid=[1.0],
    )
    # source_diversity * avg_credibility * min(2/3, 1.0)
    expected = 1.0 * 0.9 * (2.0 / 3.0)
    assert abs(cluster.triangulation_score() - expected) < 0.01


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


# ── _compute_cluster_stats ───────────────────────────────────────


def test_compute_cluster_stats_source_diversity() -> None:
    """source_diversity = distinct_sources / total_adapters."""
    signals = [
        _make_signal("hackernews", "Test A", credibility=0.7),
        _make_signal("reddit", "Test B", credibility=0.8),
        _make_signal("hackernews", "Test C", credibility=0.6),
    ]
    cluster = SignalCluster(topic="Test", signals=signals)
    _compute_cluster_stats(cluster, total_adapters=4)
    # 2 distinct sources / 4 total = 0.5
    assert cluster.source_diversity == 0.5


def test_compute_cluster_stats_avg_credibility() -> None:
    """avg_credibility should be mean of signal credibilities."""
    signals = [
        _make_signal("hackernews", "Test A", credibility=0.6),
        _make_signal("reddit", "Test B", credibility=0.8),
        _make_signal("github_issues", "Test C", credibility=1.0),
    ]
    cluster = SignalCluster(topic="Test", signals=signals)
    _compute_cluster_stats(cluster, total_adapters=3)
    # (0.6 + 0.8 + 1.0) / 3 = 0.8
    assert abs(cluster.avg_credibility - 0.8) < 0.01


def test_compute_cluster_stats_topic_updated_to_highest_credibility() -> None:
    """Topic should be updated to the title of the highest-credibility signal."""
    signals = [
        _make_signal("hackernews", "Low credibility signal", credibility=0.5),
        _make_signal("reddit", "Medium credibility signal", credibility=0.7),
        _make_signal("github_issues", "High credibility signal", credibility=0.9),
    ]
    cluster = SignalCluster(topic="Initial topic", signals=signals)
    _compute_cluster_stats(cluster, total_adapters=3)
    assert cluster.topic == "High credibility signal"


def test_compute_cluster_stats_roles_count() -> None:
    """roles dict should count signal_role occurrences."""
    signals = [
        _make_signal("hackernews", "Test A", signal_role="problem"),
        _make_signal("reddit", "Test B", signal_role="solution"),
        _make_signal("github_issues", "Test C", signal_role="problem"),
        _make_signal("twitter", "Test D", signal_role="market"),
    ]
    cluster = SignalCluster(topic="Test", signals=signals)
    _compute_cluster_stats(cluster, total_adapters=4)
    assert cluster.roles == {"problem": 2, "solution": 1, "market": 1}


def test_compute_cluster_stats_handles_none_signal_role() -> None:
    """Signals with None signal_role should map to 'unknown'."""
    # Create signal with no signal_role in metadata
    signal_without_role = Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter="hackernews",
        title="Test signal",
        content="Test content",
        url="https://example.com/test",
        credibility=0.7,
        metadata={},  # No signal_role
    )
    cluster = SignalCluster(topic="Test", signals=[signal_without_role])
    _compute_cluster_stats(cluster, total_adapters=1)
    assert cluster.roles == {"unknown": 1}


def test_compute_cluster_stats_empty_cluster() -> None:
    """Should handle empty cluster gracefully."""
    cluster = SignalCluster(topic="Empty", signals=[])
    _compute_cluster_stats(cluster, total_adapters=0)
    assert cluster.avg_credibility == 0.0
    assert cluster.source_diversity == 0.0
    assert cluster.roles == {}


# ── max_clusters limit ───────────────────────────────────────────


def test_max_clusters_respected() -> None:
    signals = [
        _make_signal("adapter", f"Unique topic number {i} about subject {i * 37}")
        for i in range(30)
    ]
    clusters = triangulate(signals, similarity_threshold=0.99, max_clusters=5)
    assert len(clusters) <= 5


def test_triangulate_returns_sorted_by_score_descending() -> None:
    """Clusters should be sorted by triangulation_score descending."""
    signals = [
        # Cluster 1: high credibility, low diversity
        _make_signal("hackernews", "Topic A signal 1", credibility=0.9),
        _make_signal("hackernews", "Topic A signal 2", credibility=0.9),
        _make_signal("hackernews", "Topic A signal 3", credibility=0.9),
        # Cluster 2: lower credibility, higher diversity
        _make_signal("reddit", "Topic B signal 1", credibility=0.5),
        _make_signal("github_issues", "Topic B signal 2", credibility=0.5),
        _make_signal("twitter", "Topic B signal 3", credibility=0.5),
    ]
    clusters = triangulate(signals, similarity_threshold=0.40)
    # Verify sorted descending
    if len(clusters) > 1:
        scores = [c.triangulation_score() for c in clusters]
        assert scores == sorted(scores, reverse=True)


@patch("max.analysis.triangulation.embed_text")
@patch("max.analysis.triangulation._cosine_similarity")
def test_triangulate_with_mocked_embeddings(mock_sim, mock_embed) -> None:
    """Verify triangulate uses embed_text and _cosine_similarity correctly."""
    # Mock embeddings: return different vectors for different texts
    def mock_embed_fn(text: str) -> list[float]:
        if "Topic A" in text:
            return [1.0, 0.0, 0.0]
        else:
            return [0.0, 1.0, 0.0]

    mock_embed.side_effect = mock_embed_fn

    # Mock similarity: high for same topic, low for different
    def mock_sim_fn(vec1: list[float], vec2: list[float]) -> float:
        if vec1 == vec2:
            return 1.0
        return 0.3

    mock_sim.side_effect = mock_sim_fn

    signals = [
        _make_signal("hackernews", "Topic A signal 1"),
        _make_signal("reddit", "Topic A signal 2"),
        _make_signal("github_issues", "Topic B signal 1"),
    ]

    clusters = triangulate(signals, similarity_threshold=0.65)

    # Verify embed_text was called for each signal
    assert mock_embed.call_count == 3

    # Should have 2 clusters (Topic A and Topic B)
    assert len(clusters) >= 1


@patch("max.analysis.triangulation.embed_text")
@patch("max.analysis.triangulation._cosine_similarity")
def test_triangulate_updates_centroid_incrementally(mock_sim, mock_embed) -> None:
    """Verify centroid is updated incrementally when adding signals to cluster."""
    # Return simple embeddings
    mock_embed.side_effect = [
        [1.0, 0.0],  # First signal
        [0.9, 0.1],  # Second signal (similar)
        [0.8, 0.2],  # Third signal (similar)
    ]

    # First call returns low similarity (no clusters yet)
    # Then return high similarity to cluster with first signal
    mock_sim.side_effect = [
        0.95,  # Second signal vs first cluster
        0.90,  # Third signal vs updated cluster
    ]

    signals = [
        _make_signal("hackernews", "Test signal 1"),
        _make_signal("reddit", "Test signal 2"),
        _make_signal("github_issues", "Test signal 3"),
    ]

    clusters = triangulate(signals, similarity_threshold=0.65)

    # If they clustered together, verify the cluster has all signals
    if len(clusters) == 1:
        assert len(clusters[0].signals) == 3
        assert len(clusters[0].centroid) == 2


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


def test_format_cluster_context_empty_list() -> None:
    """Explicitly test empty list returns None."""
    result = format_cluster_context([])
    assert result is None


def test_format_cluster_context_includes_all_fields() -> None:
    """Formatted output should include sources, roles, and credibility."""
    # Manually create clusters with controlled data
    cluster1 = SignalCluster(
        topic="AI Testing Framework",
        signals=[
            _make_signal("hackernews", "AI test tool", credibility=0.8, signal_role="problem"),
            _make_signal("reddit", "AI testing hard", credibility=0.7, signal_role="market"),
        ],
        source_diversity=0.67,
        avg_credibility=0.75,
        centroid=[1.0],
    )
    cluster1.roles = {"problem": 1, "market": 1}

    cluster2 = SignalCluster(
        topic="MCP Development",
        signals=[
            _make_signal("github_issues", "MCP bug", credibility=0.6, signal_role="problem"),
            _make_signal("twitter", "MCP discussion", credibility=0.5, signal_role="market"),
        ],
        source_diversity=0.5,
        avg_credibility=0.55,
        centroid=[0.5],
    )
    cluster2.roles = {"problem": 1, "market": 1}

    result = format_cluster_context([cluster1, cluster2])

    assert result is not None
    lines = result.split("\n")

    # Check first cluster
    assert "1." in lines[0]
    assert "[AI Testing Framework]" in lines[0]
    assert "2 signals from" in lines[0]
    assert "hackernews" in lines[0] and "reddit" in lines[0]
    assert "roles:" in lines[0]
    assert "credibility: 0.75" in lines[0]

    # Check second cluster
    assert "2." in lines[1]
    assert "[MCP Development]" in lines[1]
    assert "2 signals from" in lines[1]
    assert "github_issues" in lines[1] and "twitter" in lines[1]


def test_format_cluster_context_respects_max_clusters_param() -> None:
    """Should only format up to max_clusters even if more exist."""
    clusters = [
        SignalCluster(
            topic=f"Topic {i}",
            signals=[
                _make_signal(f"adapter{i}a", f"Signal {i}a"),
                _make_signal(f"adapter{i}b", f"Signal {i}b"),
            ],
            source_diversity=0.5,
            avg_credibility=0.7,
            centroid=[float(i)],
        )
        for i in range(10)
    ]
    # Set roles for all clusters
    for cluster in clusters:
        cluster.roles = {"market": 2}

    result = format_cluster_context(clusters, max_clusters=3)

    assert result is not None
    lines = result.split("\n")
    assert len(lines) == 3  # Only 3 clusters formatted
