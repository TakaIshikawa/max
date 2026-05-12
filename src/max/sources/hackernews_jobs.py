"""Compatibility module for Hacker News jobs source signals."""

from __future__ import annotations

from max.sources.hackernews_whoishiring import HackerNewsWhoIsHiringAdapter


class HackerNewsJobsAdapter(HackerNewsWhoIsHiringAdapter):
    """Alias for the Who is hiring? adapter using the task-requested name."""


__all__ = ["HackerNewsJobsAdapter", "HackerNewsWhoIsHiringAdapter"]
