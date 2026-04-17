"""Tests for configuration parsing and validation."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from max.config import _parse_float, _parse_int, _resolve_secret, get_project_root


class TestParseInt:
    """Tests for _parse_int helper."""

    def test_returns_default_when_env_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _parse_int("NONEXISTENT_VAR", 42) == 42

    @pytest.mark.parametrize("value", ["abc", "", " "])
    def test_returns_default_for_non_numeric(self, value):
        with patch.dict("os.environ", {"TEST_VAR": value}):
            assert _parse_int("TEST_VAR", 99) == 99

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("8080", 8080), ("0", 0), ("-1", -1)],
    )
    def test_returns_parsed_value_for_valid_strings(self, value, expected):
        with patch.dict("os.environ", {"TEST_VAR": value}):
            assert _parse_int("TEST_VAR", 99) == expected


class TestParseFloat:
    """Tests for _parse_float helper."""

    def test_returns_default_when_env_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _parse_float("NONEXISTENT_VAR", 1.5) == 1.5

    @pytest.mark.parametrize("value", ["abc", "", " "])
    def test_returns_default_for_non_numeric(self, value):
        with patch.dict("os.environ", {"TEST_VAR": value}):
            assert _parse_float("TEST_VAR", 3.14) == 3.14

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("50.5", 50.5), ("0", 0.0), ("-2.5", -2.5)],
    )
    def test_returns_parsed_value_for_valid_strings(self, value, expected):
        with patch.dict("os.environ", {"TEST_VAR": value}):
            assert _parse_float("TEST_VAR", 3.14) == expected


class TestValidateConfig:
    """Tests for validate_config()."""

    def test_warns_on_invalid_port_range(self):
        with patch("max.config.MAX_PORT", 99999), patch("max.config.ANTHROPIC_API_KEY", "sk-test"), patch("max.config.MAX_SCHEDULE_INTERVAL", 3600):
            from max.config import validate_config

            warnings = validate_config()
            assert any("MAX_PORT" in w for w in warnings)

    def test_warns_on_port_zero(self):
        with patch("max.config.MAX_PORT", 0), patch("max.config.ANTHROPIC_API_KEY", "sk-test"), patch("max.config.MAX_SCHEDULE_INTERVAL", 3600):
            from max.config import validate_config

            warnings = validate_config()
            assert any("MAX_PORT" in w for w in warnings)

    def test_warns_on_empty_api_key(self):
        with patch("max.config.ANTHROPIC_API_KEY", ""), patch("max.config.MAX_PORT", 8000), patch("max.config.MAX_SCHEDULE_INTERVAL", 3600):
            from max.config import validate_config

            warnings = validate_config()
            assert any("ANTHROPIC_API_KEY" in w for w in warnings)

    def test_warns_on_low_schedule_interval(self):
        with patch("max.config.MAX_SCHEDULE_INTERVAL", 30), patch("max.config.ANTHROPIC_API_KEY", "sk-test"), patch("max.config.MAX_PORT", 8000):
            from max.config import validate_config

            warnings = validate_config()
            assert any("MAX_SCHEDULE_INTERVAL" in w for w in warnings)

    def test_returns_empty_when_valid(self):
        with patch("max.config.ANTHROPIC_API_KEY", "sk-test"), patch("max.config.MAX_PORT", 8000), patch("max.config.MAX_SCHEDULE_INTERVAL", 3600):
            from max.config import validate_config

            assert validate_config() == []


class TestModuleLevelDefaults:
    """Module-level variables use correct defaults when env vars are unset."""

    def test_defaults_without_env_vars(self):
        env_overrides = {
            k: v
            for k, v in {
                "MAX_PORT": None,
                "MAX_SCHEDULE_INTERVAL": None,
                "MAX_SCHEDULE_SIGNAL_LIMIT": None,
                "MAX_SCHEDULE_MIN_SCORE": None,
            }.items()
        }
        # Remove these env vars entirely for the reload
        import os

        clean_env = {k: v for k, v in os.environ.items() if k not in env_overrides}
        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg

            importlib.reload(cfg)

            assert cfg.MAX_PORT == 8000
            assert cfg.MAX_SCHEDULE_INTERVAL == 21600
            assert cfg.MAX_SCHEDULE_SIGNAL_LIMIT == 30
            assert cfg.MAX_SCHEDULE_MIN_SCORE == 50.0

        # Reload with real env to restore state for other tests
        importlib.reload(cfg)


class TestResolveSecret:
    """Tests for _resolve_secret helper."""

    def test_env_var_takes_precedence(self):
        """When env var is set, vault is never called."""
        mock_run = MagicMock()
        with patch.dict("os.environ", {"TEST_SECRET": "env-value"}), patch("subprocess.run", mock_run):
            result = _resolve_secret("TEST_SECRET", "vault/path")
            assert result == "env-value"
            mock_run.assert_not_called()

    def test_vault_fallback(self):
        """When env var is empty, vault command is called and returns value."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "secret-value\n"

        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _resolve_secret("TEST_SECRET", "vault/path")
            assert result == "secret-value"
            mock_run.assert_called_once_with(
                ["vault", "get", "vault/path"],
                capture_output=True,
                text=True,
                timeout=5,
            )

    def test_vault_command_failure(self):
        """When vault command returns non-zero, returns empty string."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", return_value=mock_result):
            result = _resolve_secret("TEST_SECRET", "vault/path")
            assert result == ""

    def test_vault_not_installed(self):
        """When vault command raises FileNotFoundError, returns empty string."""
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", side_effect=FileNotFoundError):
            result = _resolve_secret("TEST_SECRET", "vault/path")
            assert result == ""

    def test_vault_timeout(self):
        """When vault command times out, returns empty string."""
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["vault"], 5)):
            result = _resolve_secret("TEST_SECRET", "vault/path")
            assert result == ""

    def test_vault_returns_empty_stdout(self):
        """When vault succeeds but returns empty stdout, returns empty string."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", return_value=mock_result):
            result = _resolve_secret("TEST_SECRET", "vault/path")
            assert result == ""


class TestCorsOrigins:
    """Tests for CORS origins parsing."""

    def test_empty_string(self):
        """Empty MAX_CORS_ORIGINS results in empty list."""
        import os

        clean_env = {k: v for k, v in os.environ.items() if k != "MAX_CORS_ORIGINS"}
        clean_env["MAX_CORS_ORIGINS"] = ""

        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg

            importlib.reload(cfg)
            assert cfg.CORS_ORIGINS == []

        importlib.reload(cfg)

    def test_single_origin(self):
        """Single origin is parsed correctly."""
        import os

        clean_env = {k: v for k, v in os.environ.items() if k != "MAX_CORS_ORIGINS"}
        clean_env["MAX_CORS_ORIGINS"] = "http://localhost:3000"

        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg

            importlib.reload(cfg)
            assert cfg.CORS_ORIGINS == ["http://localhost:3000"]

        importlib.reload(cfg)

    def test_multiple_comma_separated(self):
        """Multiple comma-separated origins are parsed correctly."""
        import os

        clean_env = {k: v for k, v in os.environ.items() if k != "MAX_CORS_ORIGINS"}
        clean_env["MAX_CORS_ORIGINS"] = "http://localhost:3000,https://example.com"

        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg

            importlib.reload(cfg)
            assert cfg.CORS_ORIGINS == ["http://localhost:3000", "https://example.com"]

        importlib.reload(cfg)

    def test_whitespace_handling(self):
        """Extra whitespace around commas is stripped."""
        import os

        clean_env = {k: v for k, v in os.environ.items() if k != "MAX_CORS_ORIGINS"}
        clean_env["MAX_CORS_ORIGINS"] = "http://localhost:3000 , https://example.com , https://another.com"

        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg

            importlib.reload(cfg)
            assert cfg.CORS_ORIGINS == ["http://localhost:3000", "https://example.com", "https://another.com"]

        importlib.reload(cfg)

    def test_trailing_comma(self):
        """Trailing comma results in single origin (empty strings filtered)."""
        import os

        clean_env = {k: v for k, v in os.environ.items() if k != "MAX_CORS_ORIGINS"}
        clean_env["MAX_CORS_ORIGINS"] = "http://localhost:3000,"

        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg

            importlib.reload(cfg)
            assert cfg.CORS_ORIGINS == ["http://localhost:3000"]

        importlib.reload(cfg)


class TestGetProjectRoot:
    """Tests for get_project_root() function."""

    def test_returns_path_object(self):
        """get_project_root() returns a Path object."""
        result = get_project_root()
        assert isinstance(result, Path)

    def test_contains_src_max_subdirectory(self):
        """Returned path contains src/max as a subdirectory."""
        root = get_project_root()
        src_max_path = root / "src" / "max"
        assert src_max_path.exists()
        assert src_max_path.is_dir()
