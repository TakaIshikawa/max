"""Profile loader — find, parse, and validate pipeline profiles from YAML files."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from max.profiles.schema import (
    DEFAULT_DOMAIN_CONTEXT,
    EvaluationConfig,
    PipelineProfile,
    SourceConfig,
)

logger = logging.getLogger(__name__)


def get_profiles_dir() -> Path:
    """Return the profiles directory (project_root/profiles/)."""
    # Walk up from this file to find the project root (where pyproject.toml lives)
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            return current / "profiles"
        current = current.parent
    # Fallback: cwd / profiles
    return Path.cwd() / "profiles"


def load_profile(name: str) -> PipelineProfile:
    """Load a profile by name from the profiles directory.

    Raises FileNotFoundError if no matching YAML file is found.
    """
    profiles_dir = get_profiles_dir()
    yaml_path = profiles_dir / f"{name}.yaml"
    if not yaml_path.exists():
        # Also try .yml extension
        yaml_path = profiles_dir / f"{name}.yml"
    if not yaml_path.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"Profile '{name}' not found in {profiles_dir}. "
            f"Available: {available or 'none'}"
        )
    return _load_yaml(yaml_path)


def get_default_profile() -> PipelineProfile:
    """Return the default devtools profile.

    Tries to load profiles/devtools.yaml first. If not found, constructs
    from code constants (backward compatible — no YAML file required).
    """
    try:
        return load_profile("devtools")
    except FileNotFoundError:
        pass

    return PipelineProfile(
        name="devtools",
        domain=DEFAULT_DOMAIN_CONTEXT,
        sources=[
            SourceConfig(adapter="hackernews"),
            SourceConfig(
                adapter="reddit",
                params={
                    "subreddits": [
                        "programming",
                        "MachineLearning",
                        "LocalLLaMA",
                        "ChatGPT",
                        "artificial",
                        "devops",
                        "ExperiencedDevs",
                    ]
                },
            ),
            SourceConfig(
                adapter="github",
                params={"topics": ["mcp", "ai-agent", "llm", "developer-tools", "cli"]},
            ),
            SourceConfig(
                adapter="github_issues",
                params={
                    "queries": [
                        '"ai agent" label:enhancement is:open sort:reactions-+1-desc',
                        '"llm" label:bug is:open sort:reactions-+1-desc',
                        '"mcp server" is:issue is:open sort:comments-desc',
                        '"ai agent" is:issue is:open sort:reactions-+1-desc',
                    ]
                },
            ),
            SourceConfig(
                adapter="npm_registry",
                params={"queries": ["mcp server", "ai agent", "llm tool", "claude"]},
            ),
            SourceConfig(
                adapter="pypi_registry",
                params={
                    "keywords": [
                        "ai", "llm", "agent", "mcp", "langchain", "openai", "anthropic",
                        "transformer", "embedding", "rag", "vector", "gpt", "claude",
                        "huggingface", "diffusion", "neural", "deep-learning",
                        "machine-learning", "chatbot", "prompt", "tokenizer", "inference",
                    ]
                },
            ),
            SourceConfig(
                adapter="security_advisories",
                params={"ecosystems": ["pip", "npm", "go"], "severities": ["critical", "high"]},
            ),
            SourceConfig(
                adapter="product_hunt",
                params={"topics": ["developer-tools", "artificial-intelligence"]},
            ),
        ],
        evaluation=EvaluationConfig(weight_profile="default", min_score=50.0),
        output_dir=".max-output",
        signal_limit=30,
        ideation_mode="direct",
    )


def list_profiles() -> list[str]:
    """List available profile names (stems of YAML files in profiles/)."""
    profiles_dir = get_profiles_dir()
    if not profiles_dir.is_dir():
        return []
    names = []
    for path in sorted(profiles_dir.iterdir()):
        if path.suffix in (".yaml", ".yml"):
            names.append(path.stem)
    return names


def _load_yaml(path: Path) -> PipelineProfile:
    """Parse a YAML file into a PipelineProfile."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile YAML (expected dict): {path}")
    return PipelineProfile(**data)
