"""Tests for triage, dedup, and cluster-based review commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from max.cli import main
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_unit(
    id: str = "bu-test001",
    title: str = "MCP Test Framework",
    status: str = "evaluated",
    category: str = BuildableCategory.CLI_TOOL,
    domain: str = "devtools",
) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=title,
        one_liner="Standardized testing for MCP servers",
        category=category,
        ideation_mode=IdeationMode.DIRECT,
        problem="No standard way to test MCP servers",
        solution="A CLI tool that validates MCP server implementations",
        target_users="both",
        value_proposition="Reduce bugs in MCP servers by 80%",
        inspiring_insights=["ins-test001"],
        evidence_signals=["sig-test001"],
        tech_approach="TypeScript CLI with protocol-level validation",
        suggested_stack={"language": "typescript", "runtime": "node"},
        composability_notes="Integrates with CI/CD pipelines",
        status=status,
        domain=domain,
    )


def _make_dim(value: float = 7.0, confidence: float = 0.7, reasoning: str = "test") -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning=reasoning)


def _make_evaluation(unit_id: str = "bu-test001", score: float = 78.0, rec: str = "yes") -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_dim(8.0),
        addressable_scale=_make_dim(7.0),
        build_effort=_make_dim(7.5),
        composability=_make_dim(8.5),
        competitive_density=_make_dim(9.0),
        timing_fit=_make_dim(8.0),
        compounding_value=_make_dim(7.0),
        overall_score=score,
        strengths=["High demand", "Low competition"],
        weaknesses=["Niche audience"],
        recommendation=rec,
        weights_used={
            "pain_severity": 0.20,
            "addressable_scale": 0.15,
            "build_effort": 0.15,
            "composability": 0.15,
            "competitive_density": 0.10,
            "timing_fit": 0.10,
            "compounding_value": 0.15,
        },
    )


def _mock_store(**overrides) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = overrides.get("units", [])
    store.get_buildable_unit.return_value = overrides.get("unit", None)
    store.get_evaluation.return_value = overrides.get("evaluation", None)
    store.has_feedback.return_value = overrides.get("has_feedback", False)
    store.get_feedback_outcomes.return_value = overrides.get("feedback_outcomes", [])
    store.close.return_value = None
    return store


# ── triage command ─────────────────────────────────────────────────


class TestTriageCommand:
    """Tests for ``max triage``."""

    @patch("max.store.db.Store")
    def test_triage_no_ideas(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(units=[])
        result = runner.invoke(main, ["triage"])
        assert result.exit_code == 0
        assert "No ideas found" in result.output

    @patch("max.store.db.Store")
    def test_triage_auto_approve_high_score(self, MockStore, runner: CliRunner) -> None:
        """Ideas with score >= 68 and rec=yes should be auto-approved."""
        unit = _make_unit(id="bu-high", title="High Scorer")
        ev = _make_evaluation("bu-high", score=75.0, rec="yes")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0
        assert "Auto-approve" in result.output
        assert "High Scorer" in result.output
        store.insert_feedback.assert_called_once()
        args = store.insert_feedback.call_args
        assert args[0][1] == "approved"
        store.update_buildable_unit_status.assert_called_once_with("bu-high", "approved")

    @patch("max.store.db.Store")
    def test_triage_auto_reject_low_score(self, MockStore, runner: CliRunner) -> None:
        """Ideas with score < 50 should be auto-rejected."""
        unit = _make_unit(id="bu-low", title="Low Scorer")
        ev = _make_evaluation("bu-low", score=42.0, rec="maybe")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0
        assert "Auto-reject" in result.output
        assert "Low Scorer" in result.output
        store.insert_feedback.assert_called_once()
        args = store.insert_feedback.call_args
        assert args[0][1] == "rejected"
        store.update_buildable_unit_status.assert_called_once_with("bu-low", "rejected")

    @patch("max.store.db.Store")
    def test_triage_auto_reject_no_recommendation(self, MockStore, runner: CliRunner) -> None:
        """Ideas with rec=no should be auto-rejected regardless of score."""
        unit = _make_unit(id="bu-no", title="No Rec")
        ev = _make_evaluation("bu-no", score=65.0, rec="no")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0
        assert "Auto-reject" in result.output
        store.update_buildable_unit_status.assert_called_once_with("bu-no", "rejected")

    @patch("max.store.db.Store")
    def test_triage_pending_middle_range(self, MockStore, runner: CliRunner) -> None:
        """Ideas in the middle range (50-68 with rec=maybe) should be pending."""
        unit = _make_unit(id="bu-mid", title="Middle Scorer")
        ev = _make_evaluation("bu-mid", score=55.0, rec="maybe")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0
        assert "No ideas matched triage thresholds" in result.output
        assert "1 ideas remain for manual review" in result.output
        store.insert_feedback.assert_not_called()

    @patch("max.store.db.Store")
    def test_triage_dry_run(self, MockStore, runner: CliRunner) -> None:
        """Dry run should not apply any changes."""
        unit = _make_unit(id="bu-high", title="High Scorer")
        ev = _make_evaluation("bu-high", score=75.0, rec="yes")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        store.insert_feedback.assert_not_called()
        store.update_buildable_unit_status.assert_not_called()

    @patch("max.store.db.Store")
    def test_triage_skips_already_reviewed(self, MockStore, runner: CliRunner) -> None:
        """Ideas with existing feedback should be skipped."""
        unit = _make_unit(id="bu-reviewed")
        ev = _make_evaluation("bu-reviewed", score=75.0, rec="yes")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = True  # Already has feedback
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0
        assert "No ideas matched" in result.output
        store.insert_feedback.assert_not_called()

    @patch("max.store.db.Store")
    def test_triage_domain_filter(self, MockStore, runner: CliRunner) -> None:
        """Domain filter should be passed to store."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        runner.invoke(main, ["triage", "--domain", "healthcare"])

        store.get_buildable_units.assert_called_once_with(limit=500, domain="healthcare")

    @patch("max.store.db.Store")
    def test_triage_custom_thresholds(self, MockStore, runner: CliRunner) -> None:
        """Custom thresholds should be respected."""
        unit = _make_unit(id="bu-custom", title="Custom Threshold")
        ev = _make_evaluation("bu-custom", score=55.0, rec="yes")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        MockStore.return_value = store

        # Lower approve threshold to 55
        result = runner.invoke(main, ["triage", "--approve-threshold", "55"])

        assert result.exit_code == 0
        assert "Auto-approve" in result.output
        store.insert_feedback.assert_called_once()

    @patch("max.store.db.Store")
    def test_triage_mixed_results(self, MockStore, runner: CliRunner) -> None:
        """Multiple ideas should be triaged correctly."""
        units = [
            _make_unit(id="bu-high", title="High"),
            _make_unit(id="bu-low", title="Low"),
            _make_unit(id="bu-mid", title="Mid"),
        ]
        evals = {
            "bu-high": _make_evaluation("bu-high", score=72.0, rec="yes"),
            "bu-low": _make_evaluation("bu-low", score=40.0, rec="no"),
            "bu-mid": _make_evaluation("bu-mid", score=55.0, rec="maybe"),
        }

        store = _mock_store(units=units)
        store.get_evaluation.side_effect = lambda uid: evals.get(uid)
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0
        assert "Auto-approve (1 ideas" in result.output
        assert "Auto-reject (1 ideas" in result.output
        assert "Pending manual review: 1 ideas" in result.output
        assert store.insert_feedback.call_count == 2
        assert store.update_buildable_unit_status.call_count == 2


# ── dedup command ──────────────────────────────────────────────────


class TestDedupCommand:
    """Tests for ``max dedup``."""

    @patch("max.store.db.Store")
    def test_dedup_no_ideas(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(units=[])
        result = runner.invoke(main, ["dedup"])
        assert result.exit_code == 0
        assert "No ideas found" in result.output

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_dedup_no_duplicates(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """All unique ideas → no action."""
        from max.analysis.dedup import IdeaCluster

        units = [_make_unit(id="bu-1", title="Unique A"), _make_unit(id="bu-2", title="Unique B")]
        evals = {
            "bu-1": _make_evaluation("bu-1", score=70.0),
            "bu-2": _make_evaluation("bu-2", score=65.0),
        }

        store = _mock_store(units=units)
        store.get_evaluation.side_effect = lambda uid: evals.get(uid)
        MockStore.return_value = store

        # Each idea in its own cluster (no duplicates)
        mock_cluster.return_value = [
            IdeaCluster(
                representative=units[0],
                representative_eval=evals["bu-1"],
                members=[(units[0], evals["bu-1"])],
                centroid=[],
            ),
            IdeaCluster(
                representative=units[1],
                representative_eval=evals["bu-2"],
                members=[(units[1], evals["bu-2"])],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["dedup"])

        assert result.exit_code == 0
        assert "No duplicates found" in result.output
        store.insert_feedback.assert_not_called()

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_dedup_marks_duplicates(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Cluster with 2 similar ideas: keep highest, mark other as duplicate."""
        from max.analysis.dedup import IdeaCluster

        unit_best = _make_unit(id="bu-best", title="Best Idea", domain="fintech")
        unit_dup = _make_unit(id="bu-dup", title="Similar Idea", domain="healthcare")
        ev_best = _make_evaluation("bu-best", score=72.0)
        ev_dup = _make_evaluation("bu-dup", score=60.0)

        store = _mock_store(units=[unit_best, unit_dup])
        store.get_evaluation.side_effect = lambda uid: {"bu-best": ev_best, "bu-dup": ev_dup}.get(uid)
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_best,
                representative_eval=ev_best,
                members=[(unit_best, ev_best), (unit_dup, ev_dup)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["dedup"])

        assert result.exit_code == 0
        assert "KEEP" in result.output
        assert "DUP" in result.output
        assert "Marked 1 ideas as duplicate" in result.output
        store.update_buildable_unit_status.assert_called_once_with("bu-dup", "duplicate")

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_dedup_dry_run(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Dry run shows duplicates but doesn't mark them."""
        from max.analysis.dedup import IdeaCluster

        unit_a = _make_unit(id="bu-a", title="Idea A")
        unit_b = _make_unit(id="bu-b", title="Idea B")
        ev_a = _make_evaluation("bu-a", score=70.0)
        ev_b = _make_evaluation("bu-b", score=60.0)

        store = _mock_store(units=[unit_a, unit_b])
        store.get_evaluation.side_effect = lambda uid: {"bu-a": ev_a, "bu-b": ev_b}.get(uid)
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_a,
                representative_eval=ev_a,
                members=[(unit_a, ev_a), (unit_b, ev_b)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["dedup", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        store.insert_feedback.assert_not_called()
        store.update_buildable_unit_status.assert_not_called()

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_dedup_preserves_approved_in_cluster(
        self, MockStore, mock_cluster, runner: CliRunner,
    ) -> None:
        """Approved members should remain representative; new evaluated peer marked as duplicate."""
        from max.analysis.dedup import IdeaCluster

        unit_approved = _make_unit(id="bu-app", title="Approved Idea", status="approved")
        unit_new = _make_unit(id="bu-new", title="New Idea", status="evaluated")
        ev_approved = _make_evaluation("bu-app", score=60.0)
        ev_new = _make_evaluation("bu-new", score=90.0)

        store = _mock_store(units=[unit_approved, unit_new])
        store.get_evaluation.side_effect = lambda uid: {
            "bu-app": ev_approved, "bu-new": ev_new,
        }.get(uid)
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_approved,
                representative_eval=ev_approved,
                members=[(unit_approved, ev_approved), (unit_new, ev_new)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["dedup"])

        assert result.exit_code == 0
        # Only the new evaluated idea should be marked
        store.update_buildable_unit_status.assert_called_once_with("bu-new", "duplicate")
        assert store.insert_feedback.call_count == 1
        assert store.insert_feedback.call_args[0][0] == "bu-new"
        assert "Marked 1" in result.output

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_dedup_skips_already_user_decided_duplicates(
        self, MockStore, mock_cluster, runner: CliRunner,
    ) -> None:
        """Already-rejected duplicates should not be re-mutated; report as preserved."""
        from max.analysis.dedup import IdeaCluster

        unit_rep = _make_unit(id="bu-rep", title="Best", status="evaluated")
        unit_already_rej = _make_unit(id="bu-rej", title="Old Reject", status="rejected")
        unit_already_app = _make_unit(id="bu-app", title="Old Approve", status="approved")
        ev_rep = _make_evaluation("bu-rep", score=72.0)
        ev_rej = _make_evaluation("bu-rej", score=60.0)
        ev_app = _make_evaluation("bu-app", score=68.0)

        store = _mock_store(units=[unit_rep, unit_already_rej, unit_already_app])
        store.get_evaluation.side_effect = lambda uid: {
            "bu-rep": ev_rep, "bu-rej": ev_rej, "bu-app": ev_app,
        }.get(uid)
        MockStore.return_value = store

        # Cluster: approved should be representative, then we have reps duplicates list
        # (reordering happens in real cluster_ideas; we simulate the post-fix behavior)
        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_already_app,
                representative_eval=ev_app,
                members=[
                    (unit_already_app, ev_app),
                    (unit_rep, ev_rep),
                    (unit_already_rej, ev_rej),
                ],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["dedup"])

        assert result.exit_code == 0
        # bu-rej is already rejected — should NOT be updated
        # bu-rep is evaluated — should be marked duplicate
        update_calls = [c.args for c in store.update_buildable_unit_status.call_args_list]
        assert ("bu-rep", "duplicate") in update_calls
        assert ("bu-rej", "duplicate") not in update_calls
        assert "Preserved 1" in result.output

    @patch("max.store.db.Store")
    def test_dedup_skips_existing_duplicates(self, MockStore, runner: CliRunner) -> None:
        """Ideas already marked as duplicate should be excluded from clustering."""
        unit_dup = _make_unit(id="bu-dup", title="Already Dup", status="duplicate")
        unit_ok = _make_unit(id="bu-ok", title="Ok Idea", status="evaluated")

        store = _mock_store(units=[unit_dup, unit_ok])
        # Only bu-ok should be processed; bu-dup has status="duplicate"
        store.get_evaluation.side_effect = lambda uid: _make_evaluation(uid, score=60.0) if uid == "bu-ok" else None
        MockStore.return_value = store

        # Patch cluster_ideas to verify only non-duplicate ideas are passed
        with patch("max.analysis.dedup.cluster_ideas") as mock_cluster:
            from max.analysis.dedup import IdeaCluster

            ev_ok = _make_evaluation("bu-ok", score=60.0)
            mock_cluster.return_value = [
                IdeaCluster(
                    representative=unit_ok,
                    representative_eval=ev_ok,
                    members=[(unit_ok, ev_ok)],
                    centroid=[],
                ),
            ]

            result = runner.invoke(main, ["dedup"])

            assert result.exit_code == 0
            # Should only pass 1 idea (not the duplicate)
            call_args = mock_cluster.call_args
            assert len(call_args[0][0]) == 1


# ── dedup clustering logic ─────────────────────────────────────────


class TestIdeaClustering:
    """Unit tests for the cluster_ideas function."""

    def test_empty_input(self) -> None:
        from max.analysis.dedup import cluster_ideas

        assert cluster_ideas([]) == []

    @patch("max.analysis.dedup.embed_text")
    def test_identical_ideas_cluster_together(self, mock_embed) -> None:
        """Ideas with identical embeddings should be in one cluster."""
        from max.analysis.dedup import cluster_ideas

        # Same embedding → similarity = 1.0
        mock_embed.return_value = [1.0, 0.0, 0.0]

        unit_a = _make_unit(id="bu-a", title="Idea A")
        unit_b = _make_unit(id="bu-b", title="Idea B")
        ev_a = _make_evaluation("bu-a", score=70.0)
        ev_b = _make_evaluation("bu-b", score=60.0)

        clusters = cluster_ideas([(unit_a, ev_a), (unit_b, ev_b)])

        assert len(clusters) == 1
        assert clusters[0].size == 2
        assert clusters[0].representative.id == "bu-a"  # Highest score

    @patch("max.analysis.dedup.embed_text")
    def test_different_ideas_separate_clusters(self, mock_embed) -> None:
        """Ideas with orthogonal embeddings should be in separate clusters."""
        from max.analysis.dedup import cluster_ideas

        embeddings = iter([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        mock_embed.side_effect = lambda _: next(embeddings)

        unit_a = _make_unit(id="bu-a", title="Idea A")
        unit_b = _make_unit(id="bu-b", title="Idea B")
        ev_a = _make_evaluation("bu-a", score=70.0)
        ev_b = _make_evaluation("bu-b", score=60.0)

        clusters = cluster_ideas([(unit_a, ev_a), (unit_b, ev_b)])

        assert len(clusters) == 2
        assert all(c.size == 1 for c in clusters)

    @patch("max.analysis.dedup.embed_text")
    def test_representative_is_highest_scored(self, mock_embed) -> None:
        """The representative should be the highest-scored idea in the cluster."""
        from max.analysis.dedup import cluster_ideas

        mock_embed.return_value = [1.0, 0.0, 0.0]

        unit_low = _make_unit(id="bu-low", title="Low")
        unit_high = _make_unit(id="bu-high", title="High")
        ev_low = _make_evaluation("bu-low", score=50.0)
        ev_high = _make_evaluation("bu-high", score=80.0)

        # Insert low-scored first
        clusters = cluster_ideas([(unit_low, ev_low), (unit_high, ev_high)])

        assert len(clusters) == 1
        assert clusters[0].representative.id == "bu-high"
        assert len(clusters[0].duplicates) == 1
        assert clusters[0].duplicates[0][0].id == "bu-low"

    @patch("max.analysis.dedup.embed_text")
    def test_approved_member_wins_representative_over_higher_score(self, mock_embed) -> None:
        """An approved member must be representative even if a higher-scored evaluated peer exists."""
        from max.analysis.dedup import cluster_ideas

        mock_embed.return_value = [1.0, 0.0, 0.0]

        unit_approved = _make_unit(id="bu-app", title="Approved", status="approved")
        unit_new = _make_unit(id="bu-new", title="New", status="evaluated")
        ev_approved = _make_evaluation("bu-app", score=60.0)
        ev_new = _make_evaluation("bu-new", score=85.0)  # higher score

        clusters = cluster_ideas([(unit_approved, ev_approved), (unit_new, ev_new)])

        assert len(clusters) == 1
        assert clusters[0].representative.id == "bu-app"  # status wins over score
        dup_ids = [u.id for u, _ in clusters[0].duplicates]
        assert dup_ids == ["bu-new"]

    @patch("max.analysis.dedup.embed_text")
    def test_rejected_member_wins_over_evaluated(self, mock_embed) -> None:
        """A rejected member outranks evaluated ideas (preserves user 'no')."""
        from max.analysis.dedup import cluster_ideas

        mock_embed.return_value = [1.0, 0.0, 0.0]

        unit_rejected = _make_unit(id="bu-rej", title="Rejected", status="rejected")
        unit_new = _make_unit(id="bu-new", title="New", status="evaluated")
        ev_rejected = _make_evaluation("bu-rej", score=55.0)
        ev_new = _make_evaluation("bu-new", score=90.0)

        clusters = cluster_ideas([(unit_rejected, ev_rejected), (unit_new, ev_new)])

        assert len(clusters) == 1
        assert clusters[0].representative.id == "bu-rej"

    @patch("max.analysis.dedup.embed_text")
    def test_approved_beats_rejected(self, mock_embed) -> None:
        """Approved outranks rejected when both exist in same cluster."""
        from max.analysis.dedup import cluster_ideas

        mock_embed.return_value = [1.0, 0.0, 0.0]

        unit_rejected = _make_unit(id="bu-rej", title="Rejected", status="rejected")
        unit_approved = _make_unit(id="bu-app", title="Approved", status="approved")
        ev_rejected = _make_evaluation("bu-rej", score=80.0)  # higher score
        ev_approved = _make_evaluation("bu-app", score=60.0)

        clusters = cluster_ideas([(unit_rejected, ev_rejected), (unit_approved, ev_approved)])

        assert len(clusters) == 1
        assert clusters[0].representative.id == "bu-app"

    @patch("max.analysis.dedup.embed_text")
    def test_score_breaks_ties_within_same_status(self, mock_embed) -> None:
        """Within same status priority, highest score still wins."""
        from max.analysis.dedup import cluster_ideas

        mock_embed.return_value = [1.0, 0.0, 0.0]

        unit_a = _make_unit(id="bu-a", title="Approved A", status="approved")
        unit_b = _make_unit(id="bu-b", title="Approved B", status="approved")
        ev_a = _make_evaluation("bu-a", score=70.0)
        ev_b = _make_evaluation("bu-b", score=85.0)

        clusters = cluster_ideas([(unit_a, ev_a), (unit_b, ev_b)])

        assert len(clusters) == 1
        assert clusters[0].representative.id == "bu-b"  # higher score among approved


# ── review command (cluster-based) ─────────────────────────────────


class TestReviewCommand:
    """Tests for ``max review`` with cluster-based batch review."""

    @patch("max.store.db.Store")
    def test_review_no_ideas(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(units=[])
        result = runner.invoke(main, ["review"])
        assert result.exit_code == 0
        assert "No ideas found" in result.output

    @patch("max.store.db.Store")
    def test_review_no_pending(self, MockStore, runner: CliRunner) -> None:
        """All ideas already reviewed → nothing to do."""
        unit = _make_unit(id="bu-reviewed")
        ev = _make_evaluation("bu-reviewed", score=70.0)

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = True  # All reviewed
        MockStore.return_value = store

        result = runner.invoke(main, ["review"])

        assert result.exit_code == 0
        assert "No ideas pending review" in result.output

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_single_idea_approve(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Single idea (no cluster) can be approved with 'a'."""
        from max.analysis.dedup import IdeaCluster

        unit = _make_unit(id="bu-single", title="Solo Idea", domain="devtools")
        ev = _make_evaluation("bu-single", score=65.0, rec="maybe")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit,
                representative_eval=ev,
                members=[(unit, ev)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="a\n7\n\n")

        assert result.exit_code == 0
        assert "Solo Idea" in result.output
        assert "approved" in result.output
        store.insert_feedback.assert_called_once()
        assert store.insert_feedback.call_args[0][1] == "approved"
        assert store.insert_feedback.call_args[1]["approval_score"] == 7

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_single_idea_reject(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Single idea can be rejected with 'r'."""
        from max.analysis.dedup import IdeaCluster

        unit = _make_unit(id="bu-rej", title="Bad Idea")
        ev = _make_evaluation("bu-rej", score=55.0, rec="maybe")

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit,
                representative_eval=ev,
                members=[(unit, ev)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="r\n\n")

        assert result.exit_code == 0
        assert "rejected" in result.output
        store.insert_feedback.assert_called_once()
        assert store.insert_feedback.call_args[0][1] == "rejected"

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_cluster_approve_best(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Cluster action 'a' approves best, rejects rest."""
        from max.analysis.dedup import IdeaCluster

        unit_best = _make_unit(id="bu-best", title="Best", domain="fintech")
        unit_other = _make_unit(id="bu-other", title="Other", domain="healthcare")
        ev_best = _make_evaluation("bu-best", score=72.0)
        ev_other = _make_evaluation("bu-other", score=60.0)

        store = _mock_store(units=[unit_best, unit_other])
        store.get_evaluation.side_effect = lambda uid: {"bu-best": ev_best, "bu-other": ev_other}.get(uid)
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_best,
                representative_eval=ev_best,
                members=[(unit_best, ev_best), (unit_other, ev_other)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="a\n8\n\n")

        assert result.exit_code == 0
        assert "approved best" in result.output
        assert "rejected 1 others" in result.output
        # Best approved, other rejected
        assert store.insert_feedback.call_count == 2
        calls = store.insert_feedback.call_args_list
        assert calls[0][1]["approval_score"] == 8
        assert calls[0][0][1] == "approved"
        assert calls[1][0][1] == "rejected"

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_cluster_approve_all(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Cluster action 'A' approves all members."""
        from max.analysis.dedup import IdeaCluster

        unit_a = _make_unit(id="bu-a", title="Idea A")
        unit_b = _make_unit(id="bu-b", title="Idea B")
        ev_a = _make_evaluation("bu-a", score=70.0)
        ev_b = _make_evaluation("bu-b", score=65.0)

        store = _mock_store(units=[unit_a, unit_b])
        store.get_evaluation.side_effect = lambda uid: {"bu-a": ev_a, "bu-b": ev_b}.get(uid)
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_a,
                representative_eval=ev_a,
                members=[(unit_a, ev_a), (unit_b, ev_b)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="A\n9\n\n")

        assert result.exit_code == 0
        assert "approved all 2 ideas" in result.output
        assert store.insert_feedback.call_count == 2
        for call in store.insert_feedback.call_args_list:
            assert call[0][1] == "approved"
            assert call[1]["approval_score"] == 9

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_cluster_reject_all(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Cluster action 'r' rejects all members."""
        from max.analysis.dedup import IdeaCluster

        unit_a = _make_unit(id="bu-a", title="Idea A")
        unit_b = _make_unit(id="bu-b", title="Idea B")
        ev_a = _make_evaluation("bu-a", score=55.0, rec="maybe")
        ev_b = _make_evaluation("bu-b", score=50.0, rec="maybe")

        store = _mock_store(units=[unit_a, unit_b])
        store.get_evaluation.side_effect = lambda uid: {"bu-a": ev_a, "bu-b": ev_b}.get(uid)
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_a,
                representative_eval=ev_a,
                members=[(unit_a, ev_a), (unit_b, ev_b)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="r\n\n")

        assert result.exit_code == 0
        assert "rejected all 2 ideas" in result.output
        assert store.insert_feedback.call_count == 2
        for call in store.insert_feedback.call_args_list:
            assert call[0][1] == "rejected"

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_quit(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Pressing 'q' should stop the review."""
        from max.analysis.dedup import IdeaCluster

        unit = _make_unit(id="bu-quit", title="Quit Idea")
        ev = _make_evaluation("bu-quit", score=60.0)

        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = ev
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit,
                representative_eval=ev,
                members=[(unit, ev)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="q\n")

        assert result.exit_code == 0
        assert "Review complete" in result.output
        store.insert_feedback.assert_not_called()

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_review_shows_cluster_info(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Cluster review should show cluster header with member count."""
        from max.analysis.dedup import IdeaCluster

        unit_a = _make_unit(id="bu-a", title="Idea A", domain="fintech")
        unit_b = _make_unit(id="bu-b", title="Idea B", domain="healthcare")
        ev_a = _make_evaluation("bu-a", score=70.0)
        ev_b = _make_evaluation("bu-b", score=65.0)

        store = _mock_store(units=[unit_a, unit_b])
        store.get_evaluation.side_effect = lambda uid: {"bu-a": ev_a, "bu-b": ev_b}.get(uid)
        store.has_feedback.return_value = False
        store.get_feedback_outcomes.return_value = []
        MockStore.return_value = store

        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit_a,
                representative_eval=ev_a,
                members=[(unit_a, ev_a), (unit_b, ev_b)],
                centroid=[],
            ),
        ]

        result = runner.invoke(main, ["review"], input="s\n")

        assert result.exit_code == 0
        assert "2 similar ideas" in result.output
        assert "BEST:" in result.output
        assert "also:" in result.output
