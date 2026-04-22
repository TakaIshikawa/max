"""Tact-compatible spec preview generation."""

from max.spec.generator import generate_spec_preview
from max.spec.readiness import evaluate_spec_readiness

__all__ = ["evaluate_spec_readiness", "generate_spec_preview"]
