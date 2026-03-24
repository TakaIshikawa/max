"""Tests for the tact file writer."""

from __future__ import annotations

from pathlib import Path

import yaml

from max.publisher.file_writer import write_tact_spec
from max.types.tact_spec import TactSpec


def test_write_tact_spec_creates_files(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    assert (output_dir / "product.yaml").exists()
    assert (output_dir / "architecture.yaml").exists()
    assert (output_dir / "requirements").is_dir()

    req_files = list((output_dir / "requirements").glob("REQ-*.yaml"))
    assert len(req_files) == 1


def test_product_yaml_uses_camel_case(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    with open(output_dir / "product.yaml") as f:
        data = yaml.safe_load(f)

    assert "techStack" in data
    assert data["name"] == "mcp-test-framework"
    assert data["goals"][0]["successCriteria"] == "100% of MCP protocol methods covered"


def test_requirement_yaml_has_acceptance_criteria(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    req_files = list((output_dir / "requirements").glob("REQ-*.yaml"))
    with open(req_files[0]) as f:
        data = yaml.safe_load(f)

    assert "acceptanceCriteria" in data
    assert len(data["acceptanceCriteria"]) == 3
    assert data["priority"] == "critical"
