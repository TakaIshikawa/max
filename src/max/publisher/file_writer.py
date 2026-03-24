"""Tact file writer — writes TactSpec to .tact/ directory structure."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from max.types.tact_spec import TactSpec


def write_tact_spec(spec: TactSpec, output_dir: Path) -> Path:
    """Write a TactSpec to a .tact/ directory at output_dir.

    Creates:
        output_dir/product.yaml
        output_dir/architecture.yaml
        output_dir/requirements/REQ-001.yaml, REQ-002.yaml, ...

    Returns the output_dir path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    req_dir = output_dir / "requirements"
    req_dir.mkdir(exist_ok=True)

    # Product
    product_data = spec.product.model_dump(by_alias=True)
    _write_yaml(output_dir / "product.yaml", product_data)

    # Architecture
    arch_data = spec.architecture.model_dump(by_alias=True)
    _write_yaml(output_dir / "architecture.yaml", arch_data)

    # Requirements
    for i, req in enumerate(spec.requirements, start=1):
        req_data = req.model_dump(by_alias=True)
        slug = _slugify(req.title)
        filename = f"REQ-{i:03d}-{slug}.yaml"
        _write_yaml(req_dir / filename, req_data)

    return output_dir


def _write_yaml(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _slugify(text: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length].rstrip("-")
