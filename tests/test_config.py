"""Tests for configuration parsing and validation."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from max.config import _parse_float, _parse_int


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
