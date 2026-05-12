"""Compatibility module for the Dev.to source adapter."""

from __future__ import annotations

from max.sources.devto import DevtoAdapter


class DevToAdapter(DevtoAdapter):
    """Alias using the task-requested class spelling."""


__all__ = ["DevToAdapter", "DevtoAdapter"]
