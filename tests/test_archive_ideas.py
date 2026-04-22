"""Tests for the ``max archive-ideas`` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from max.cli import main
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_focus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)
    return tmp_path / ".max" / "focus.yaml"


def _make_unit(id: str, domain: str, status: str = "evaluated") -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=f"Title for {id}",
        one_liner=f"One liner for {id}",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Some problem",
        solution="Some solution",
        target_users="developers",
        value_proposition="Some value",
        inspiring_insights=[],
        evidence_signals=[],
        tech_approach="Some approach",
        suggested_stack={},
        composability_notes="",
        status=status,
        domain=domain,
    )


class TestArchiveIdeas:
    def test_errors_when_no_focus_configured(
        self, runner: CliRunner, isolated_focus: Path,
    ) -> None:
        assert not isolated_focus.exists()
        result = runner.invoke(main, ["archive-ideas"])
        assert result.exit_code != 0
        assert "No focus domains configured" in result.output

    @patch("max.store.db.Store")
    def test_archives_out_of_focus_pending(
        self,
        MockStore: MagicMock,
        runner: CliRunner,
        isolated_focus: Path,
    ) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools", "healthcare"])

        u1 = _make_unit("bu-1", "legaltech", status="evaluated")  # archive
        u2 = _make_unit("bu-2", "developer-tools", status="evaluated")  # keep (in focus)
        u3 = _make_unit("bu-3", "fintech", status="evaluated")  # archive

        store = MagicMock()
        store.get_buildable_units.return_value = [u1, u2, u3]
        store.has_feedback.return_value = False
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["archive-ideas"])

        assert result.exit_code == 0, result.output
        # 2 archived, both out-of-focus
        assert "Archived 2 ideas" in result.output
        calls = store.update_buildable_unit_status.call_args_list
        archived_ids = {c.args[0] for c in calls}
        assert archived_ids == {"bu-1", "bu-3"}
        for c in calls:
            assert c.args[1] == "archived"

    @patch("max.store.db.Store")
    def test_preserves_approved_rejected_duplicate(
        self,
        MockStore: MagicMock,
        runner: CliRunner,
        isolated_focus: Path,
    ) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools"])

        u_approved = _make_unit("bu-a", "legaltech", status="approved")
        u_rejected = _make_unit("bu-r", "legaltech", status="rejected")
        u_dup = _make_unit("bu-d", "legaltech", status="duplicate")
        u_synth = _make_unit("bu-s", "legaltech", status="synthesized")
        u_pending = _make_unit("bu-p", "legaltech", status="evaluated")

        store = MagicMock()
        store.get_buildable_units.return_value = [
            u_approved, u_rejected, u_dup, u_synth, u_pending,
        ]
        store.has_feedback.return_value = False
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["archive-ideas"])

        assert result.exit_code == 0, result.output
        calls = store.update_buildable_unit_status.call_args_list
        archived_ids = {c.args[0] for c in calls}
        # Only the evaluated/pending unit is archived
        assert archived_ids == {"bu-p"}

    @patch("max.store.db.Store")
    def test_skips_units_with_existing_feedback(
        self,
        MockStore: MagicMock,
        runner: CliRunner,
        isolated_focus: Path,
    ) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools"])

        u = _make_unit("bu-1", "legaltech", status="evaluated")

        store = MagicMock()
        store.get_buildable_units.return_value = [u]
        store.has_feedback.return_value = True  # already reviewed
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["archive-ideas"])

        assert result.exit_code == 0, result.output
        assert "No pending ideas to archive" in result.output
        store.update_buildable_unit_status.assert_not_called()

    @patch("max.store.db.Store")
    def test_leaves_in_focus_ideas_alone(
        self,
        MockStore: MagicMock,
        runner: CliRunner,
        isolated_focus: Path,
    ) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools", "healthcare"])

        u1 = _make_unit("bu-1", "developer-tools", status="evaluated")
        u2 = _make_unit("bu-2", "healthcare", status="evaluated")

        store = MagicMock()
        store.get_buildable_units.return_value = [u1, u2]
        store.has_feedback.return_value = False
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["archive-ideas"])

        assert result.exit_code == 0, result.output
        assert "No pending ideas to archive" in result.output
        store.update_buildable_unit_status.assert_not_called()

    @patch("max.store.db.Store")
    def test_dry_run_makes_no_mutations(
        self,
        MockStore: MagicMock,
        runner: CliRunner,
        isolated_focus: Path,
    ) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools"])

        u = _make_unit("bu-1", "legaltech", status="evaluated")

        store = MagicMock()
        store.get_buildable_units.return_value = [u]
        store.has_feedback.return_value = False
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["archive-ideas", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Candidates to archive: 1" in result.output
        store.update_buildable_unit_status.assert_not_called()
        store.insert_feedback.assert_not_called()
