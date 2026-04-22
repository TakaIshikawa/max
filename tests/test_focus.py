"""Tests for the focus-domains config module (max.focus)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from max.focus import (
    get_focus_config_path,
    in_focus,
    load_focus_domains,
    save_focus_domains,
)


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
