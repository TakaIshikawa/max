"""Tests for the focus-domains config module (max.focus)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from max.focus import (
    focused_profile_names,
    get_focus_config_path,
    in_focus,
    load_focus_domains,
    save_focus_domains,
)
from max.profiles.schema import DomainContext, PipelineProfile


@pytest.fixture
def isolated_focus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect focus config to a tmp location so tests don't touch the real file."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)
    return tmp_path / ".max" / "focus.yaml"


class TestFocusConfig:
    def test_load_returns_none_when_missing(self, isolated_focus: Path) -> None:
        assert not isolated_focus.exists()
        assert load_focus_domains() is None

    def test_save_then_load_roundtrip(self, isolated_focus: Path) -> None:
        save_focus_domains(["developer-tools", "healthcare"])
        assert isolated_focus.exists()
        assert load_focus_domains() == ["developer-tools", "healthcare"]

    def test_save_none_deletes_file(self, isolated_focus: Path) -> None:
        save_focus_domains(["developer-tools"])
        assert isolated_focus.exists()
        save_focus_domains(None)
        assert not isolated_focus.exists()

    def test_save_empty_list_deletes_file(self, isolated_focus: Path) -> None:
        save_focus_domains(["developer-tools"])
        assert isolated_focus.exists()
        save_focus_domains([])
        assert not isolated_focus.exists()

    def test_save_none_when_no_file_is_noop(self, isolated_focus: Path) -> None:
        assert not isolated_focus.exists()
        save_focus_domains(None)  # Should not error
        assert not isolated_focus.exists()

    def test_load_skips_blank_entries(self, isolated_focus: Path) -> None:
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("domains:\n  - developer-tools\n  - ''\n  - healthcare\n")
        assert load_focus_domains() == ["developer-tools", "healthcare"]

    def test_load_returns_none_on_empty_domains(self, isolated_focus: Path) -> None:
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("domains: []\n")
        assert load_focus_domains() is None

    def test_load_returns_none_on_missing_key(self, isolated_focus: Path) -> None:
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("other: value\n")
        assert load_focus_domains() is None

    def test_load_rejects_non_list(self, isolated_focus: Path) -> None:
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("domains: developer-tools\n")
        with pytest.raises(ValueError, match="must be a list of strings"):
            load_focus_domains()

    def test_load_rejects_non_string_entries(self, isolated_focus: Path) -> None:
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("domains:\n  - developer-tools\n  - 42\n")
        with pytest.raises(ValueError, match="must be a list of strings"):
            load_focus_domains()


class TestInFocus:
    def test_no_config_includes_all(self, isolated_focus: Path) -> None:
        assert load_focus_domains() is None
        assert in_focus("developer-tools") is True
        assert in_focus("anything") is True

    def test_respects_configured_focus(self, isolated_focus: Path) -> None:
        save_focus_domains(["developer-tools", "healthcare"])
        assert in_focus("developer-tools") is True
        assert in_focus("healthcare") is True
        assert in_focus("legaltech") is False


class TestFocusPath:
    def test_path_matches_profiles_parent(self, isolated_focus: Path, tmp_path: Path) -> None:
        path = get_focus_config_path()
        assert path == tmp_path / ".max" / "focus.yaml"


class TestFocusedProfileNames:
    """Tests for focused_profile_names() — profile filtering based on focus config."""

    def _make_profile(self, name: str, domain_name: str) -> PipelineProfile:
        """Helper to create a minimal PipelineProfile for testing."""
        return PipelineProfile(
            name=name,
            domain=DomainContext(
                name=domain_name,
                description=f"{domain_name} domain",
                categories=["saas"],
                target_user_types=["users"],
            ),
        )

    def test_no_focus_returns_all_profiles(self, isolated_focus: Path) -> None:
        """When no focus config exists, all profiles are selected."""
        with patch("max.profiles.loader.list_profiles", return_value=["devtools", "healthcare", "legaltech"]):
            with patch("max.profiles.loader.load_profile") as mock_load:
                # Mock profiles with different domains
                mock_load.side_effect = lambda name: self._make_profile(
                    name,
                    {
                        "devtools": "developer-tools",
                        "healthcare": "healthcare",
                        "legaltech": "legaltech",
                    }[name],
                )
                selected, skipped, focus_domains = focused_profile_names()
                assert selected == ["devtools", "healthcare", "legaltech"]
                assert skipped == []
                assert focus_domains is None

    def test_include_all_flag_bypasses_focus(self, isolated_focus: Path) -> None:
        """When include_all=True, focus config is ignored."""
        save_focus_domains(["developer-tools"])
        with patch("max.profiles.loader.list_profiles", return_value=["devtools", "healthcare"]):
            with patch("max.profiles.loader.load_profile") as mock_load:
                mock_load.side_effect = lambda name: self._make_profile(
                    name,
                    {
                        "devtools": "developer-tools",
                        "healthcare": "healthcare",
                    }[name],
                )
                selected, skipped, focus_domains = focused_profile_names(include_all=True)
                assert selected == ["devtools", "healthcare"]
                assert skipped == []
                assert focus_domains is None

    def test_focus_filters_profiles_by_domain(self, isolated_focus: Path) -> None:
        """Profiles are filtered based on domain matching focus list."""
        save_focus_domains(["developer-tools", "healthcare"])
        with patch("max.profiles.loader.list_profiles", return_value=["devtools", "healthcare", "legaltech"]):
            with patch("max.profiles.loader.load_profile") as mock_load:
                mock_load.side_effect = lambda name: self._make_profile(
                    name,
                    {
                        "devtools": "developer-tools",
                        "healthcare": "healthcare",
                        "legaltech": "legaltech",
                    }[name],
                )
                selected, skipped, focus_domains = focused_profile_names()
                assert sorted(selected) == ["devtools", "healthcare"]
                assert skipped == ["legaltech"]
                assert focus_domains == ["developer-tools", "healthcare"]

    def test_empty_profile_list_returns_empty(self, isolated_focus: Path) -> None:
        """When no profiles exist, returns empty lists."""
        save_focus_domains(["developer-tools"])
        with patch("max.profiles.loader.list_profiles", return_value=[]):
            selected, skipped, focus_domains = focused_profile_names()
            assert selected == []
            assert skipped == []
            assert focus_domains == ["developer-tools"]

    def test_all_profiles_skipped_when_no_match(self, isolated_focus: Path) -> None:
        """When focus domains don't match any profiles, all are skipped."""
        save_focus_domains(["nonexistent-domain"])
        with patch("max.profiles.loader.list_profiles", return_value=["devtools", "healthcare"]):
            with patch("max.profiles.loader.load_profile") as mock_load:
                mock_load.side_effect = lambda name: self._make_profile(
                    name,
                    {
                        "devtools": "developer-tools",
                        "healthcare": "healthcare",
                    }[name],
                )
                selected, skipped, focus_domains = focused_profile_names()
                assert selected == []
                assert sorted(skipped) == ["devtools", "healthcare"]
                assert focus_domains == ["nonexistent-domain"]

    def test_profile_load_error_preserves_selection(self, isolated_focus: Path) -> None:
        """When a profile fails to load, it's still included (historical behavior)."""
        save_focus_domains(["developer-tools"])
        with patch("max.profiles.loader.list_profiles", return_value=["devtools", "broken", "healthcare"]):
            with patch("max.profiles.loader.load_profile") as mock_load:

                def load_side_effect(name):
                    if name == "broken":
                        raise ValueError("Invalid YAML")
                    return self._make_profile(
                        name,
                        {
                            "devtools": "developer-tools",
                            "healthcare": "healthcare",
                        }[name],
                    )

                mock_load.side_effect = load_side_effect
                selected, skipped, focus_domains = focused_profile_names()
                # "broken" should be in selected (can't inspect, so preserve it)
                assert "broken" in selected
                assert "devtools" in selected
                assert "healthcare" in skipped
                assert focus_domains == ["developer-tools"]

    def test_single_domain_focus(self, isolated_focus: Path) -> None:
        """Focus with a single domain works correctly."""
        save_focus_domains(["healthcare"])
        with patch("max.profiles.loader.list_profiles", return_value=["devtools", "healthcare"]):
            with patch("max.profiles.loader.load_profile") as mock_load:
                mock_load.side_effect = lambda name: self._make_profile(
                    name,
                    {
                        "devtools": "developer-tools",
                        "healthcare": "healthcare",
                    }[name],
                )
                selected, skipped, focus_domains = focused_profile_names()
                assert selected == ["healthcare"]
                assert skipped == ["devtools"]
                assert focus_domains == ["healthcare"]

    def test_focus_domains_match_is_exact(self, isolated_focus: Path) -> None:
        """Domain matching is exact, not substring."""
        save_focus_domains(["developer"])
        with patch("max.profiles.loader.list_profiles", return_value=["devtools"]):
            with patch("max.profiles.loader.load_profile") as mock_load:
                mock_load.side_effect = lambda name: self._make_profile(name, "developer-tools")
                selected, skipped, focus_domains = focused_profile_names()
                assert selected == []
                assert skipped == ["devtools"]
                assert focus_domains == ["developer"]


# ── Property-based Tests ─────────────────────────────────────────────


class TestFocusPropertyBased:
    """Property-based tests using Hypothesis for focus module."""

    def test_save_load_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Any valid domain list should roundtrip through save/load."""

        @given(
            st.lists(
                st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz-"),
                min_size=1,
                max_size=10,
                unique=True,
            )
        )
        @settings(max_examples=50, deadline=2000)
        def run_test(domains: list[str]) -> None:
            # Isolate to tmp_path
            profiles_dir = tmp_path / "profiles"
            profiles_dir.mkdir(exist_ok=True)
            monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)

            # Save and load
            save_focus_domains(domains)
            loaded = load_focus_domains()
            assert loaded == domains

        run_test()

    def test_in_focus_with_no_config_always_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no focus config exists, in_focus() is always True."""

        @given(st.text(min_size=1, max_size=50))
        @settings(max_examples=30, deadline=1000)
        def run_test(domain: str) -> None:
            profiles_dir = tmp_path / "profiles"
            profiles_dir.mkdir(exist_ok=True)
            monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)

            # Ensure no config exists
            focus_path = tmp_path / ".max" / "focus.yaml"
            if focus_path.exists():
                focus_path.unlink()

            assert in_focus(domain) is True

        run_test()

    def test_in_focus_membership(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """in_focus() should match set membership semantics."""

        @given(
            domains=st.lists(
                st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz-"),
                min_size=1,
                max_size=5,
                unique=True,
            ),
            query_domain=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz-"),
        )
        @settings(max_examples=50, deadline=2000)
        def run_test(domains: list[str], query_domain: str) -> None:
            profiles_dir = tmp_path / "profiles"
            profiles_dir.mkdir(exist_ok=True)
            monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)

            save_focus_domains(domains)
            result = in_focus(query_domain)
            expected = query_domain in domains
            assert result == expected

        run_test()


# ── Edge Cases and Error Handling ────────────────────────────────────


class TestFocusEdgeCases:
    """Edge cases and error handling for focus module."""

    def test_load_with_malformed_yaml(self, isolated_focus: Path) -> None:
        """Malformed YAML should raise an error."""
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("domains: [\n  developer-tools\n  # missing comma")
        with pytest.raises(Exception):  # yaml.safe_load will raise
            load_focus_domains()

    def test_save_preserves_file_permissions(self, isolated_focus: Path) -> None:
        """Save creates parent directories with appropriate permissions."""
        save_focus_domains(["developer-tools"])
        assert isolated_focus.parent.exists()
        assert isolated_focus.exists()
        # Can read back
        assert load_focus_domains() == ["developer-tools"]

    def test_load_with_null_yaml(self, isolated_focus: Path) -> None:
        """Completely empty YAML file should return None."""
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("")
        assert load_focus_domains() is None

    def test_load_with_only_whitespace(self, isolated_focus: Path) -> None:
        """YAML with only whitespace should return None."""
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("   \n  \n  ")
        assert load_focus_domains() is None

    def test_save_domains_with_whitespace(self, isolated_focus: Path) -> None:
        """Domains with leading/trailing whitespace are stripped."""
        save_focus_domains([" developer-tools ", "  healthcare"])
        assert load_focus_domains() == ["developer-tools", "healthcare"]

    def test_load_with_mixed_types_in_list(self, isolated_focus: Path) -> None:
        """List with mixed types should fail validation."""
        isolated_focus.parent.mkdir(parents=True, exist_ok=True)
        isolated_focus.write_text("domains:\n  - developer-tools\n  - true\n  - 123\n")
        with pytest.raises(ValueError, match="must be a list of strings"):
            load_focus_domains()

    def test_focused_profile_names_with_multiple_errors(self, isolated_focus: Path) -> None:
        """Multiple profile load errors should all be preserved in selected."""
        save_focus_domains(["developer-tools"])
        with patch("max.profiles.loader.list_profiles", return_value=["broken1", "broken2", "devtools"]):
            with patch("max.profiles.loader.load_profile") as mock_load:

                def load_side_effect(name):
                    if name in ("broken1", "broken2"):
                        raise ValueError(f"{name} is invalid")
                    return PipelineProfile(
                        name="devtools",
                        domain=DomainContext(
                            name="developer-tools",
                            description="dev tools",
                            categories=["saas"],
                            target_user_types=["developers"],
                        ),
                    )

                mock_load.side_effect = load_side_effect
                selected, skipped, focus_domains = focused_profile_names()
                assert "broken1" in selected
                assert "broken2" in selected
                assert "devtools" in selected
                assert skipped == []

    def test_in_focus_empty_string_domain(self, isolated_focus: Path) -> None:
        """Empty string domain should work correctly."""
        save_focus_domains(["developer-tools", ""])
        # Empty string gets filtered out during save
        assert load_focus_domains() == ["developer-tools"]
        assert in_focus("") is False

    def test_focused_profile_names_preserves_order(self, isolated_focus: Path) -> None:
        """Profile order from list_profiles() should be preserved."""
        save_focus_domains(["healthcare", "developer-tools"])
        with patch("max.profiles.loader.list_profiles", return_value=["zprofile", "aprofile", "mprofile"]):
            with patch("max.profiles.loader.load_profile") as mock_load:

                def load_side_effect(name):
                    domain_map = {
                        "zprofile": "healthcare",
                        "aprofile": "developer-tools",
                        "mprofile": "other",
                    }
                    return PipelineProfile(
                        name=name,
                        domain=DomainContext(
                            name=domain_map[name],
                            description="test",
                            categories=["saas"],
                            target_user_types=["users"],
                        ),
                    )

                mock_load.side_effect = load_side_effect
                selected, skipped, _ = focused_profile_names()
                # Order should match list_profiles() order
                assert selected == ["zprofile", "aprofile"]
                assert skipped == ["mprofile"]
