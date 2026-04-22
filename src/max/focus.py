"""Reviewer focus domains — scope idea generation and review to domains the
reviewer can meaningfully evaluate.

When focus is set, `max run --profile all` skips out-of-focus profiles and
`max archive-ideas` moves pending out-of-focus ideas to `status="archived"`.
An absent config file means no filter (include all domains).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from max.profiles.loader import get_profiles_dir


def get_focus_config_path() -> Path:
    """Return the focus config path (project_root/.max/focus.yaml)."""
    project_root = get_profiles_dir().parent
    return project_root / ".max" / "focus.yaml"


def load_focus_domains() -> list[str] | None:
    """Return the configured focus domains, or None if no filter is set.

    None means "include all domains" (current default behavior).
    """
    path = get_focus_config_path()
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    domains = data.get("domains")
    if not domains:
        return None
    if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
        raise ValueError(
            f"Invalid focus config at {path}: 'domains' must be a list of strings"
        )
    return [d.strip() for d in domains if d.strip()]


def save_focus_domains(domains: list[str] | None) -> None:
    """Persist focus domains. None or empty list removes the config file."""
    path = get_focus_config_path()
    if not domains:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump({"domains": list(domains)}, f, default_flow_style=False)


def in_focus(domain: str) -> bool:
    """True if no filter is set, or if *domain* is in the focus list."""
    focus = load_focus_domains()
    if focus is None:
        return True
    return domain in focus
