"""GitHub Issues source adapter — AI/ML pain points from issue trackers."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_DEFAULT_QUERIES = [
    '"ai agent" label:enhancement is:open sort:reactions-+1-desc',
    '"llm" label:bug is:open sort:reactions-+1-desc',
    '"mcp server" is:issue is:open sort:comments-desc',
    '"ai agent" is:issue is:open sort:reactions-+1-desc',
]


class GitHubIssuesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_issues"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def queries(self) -> list[str]:
        return self._config.get("queries", _DEFAULT_QUERIES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        queries = self.queries
        per_query = max(limit // len(queries), 5)

        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            try:
                import subprocess
                result = subprocess.run(
                    ["vault", "get", "github/token"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    token = result.stdout.strip()
            except Exception:
                pass
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for i, query in enumerate(queries):
                if len(signals) >= limit:
                    break

                # Rate-limit courtesy pause between queries
                if i > 0:
                    await asyncio.sleep(1)

                try:
                    resp = await client.get(
                        f"{GITHUB_API}/search/issues",
                        params={"q": query, "per_page": per_query},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    logger.warning("GitHub Issues search failed for query: %s", query, exc_info=True)
                    continue

                for item in data.get("items", []):
                    # Skip pull requests
                    if "pull_request" in item:
                        continue

                    html_url = item.get("html_url", "")
                    if html_url in seen_urls:
                        continue
                    seen_urls.add(html_url)

                    if len(signals) >= limit:
                        break

                    reactions = item.get("reactions", {}).get("total_count", 0)
                    comments = item.get("comments", 0)
                    credibility = min((reactions + comments) / 100, 1.0)

                    labels = [lbl.get("name", "") for lbl in item.get("labels", [])]
                    title = item.get("title", "")
                    body = (item.get("body") or "")[:1000]

                    # Extract repo from URL: .../repos/owner/repo/issues/N
                    repo = _extract_repo(html_url)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.FORUM,
                            source_adapter=self.name,
                            title=title,
                            content=body if body else title,
                            url=html_url,
                            author=item.get("user", {}).get("login"),
                            published_at=_parse_dt(item.get("created_at")),
                            tags=_build_tags(labels, title),
                            credibility=credibility,
                            metadata={
                                "github_issue_id": item.get("id"),
                                "repo": repo,
                                "labels": labels[:10],
                                "state": item.get("state"),
                                "reactions": reactions,
                                "comments": comments,
                                "search_query": query,
                            },
                        )
                    )

        return signals[:limit]


def _extract_repo(html_url: str) -> str:
    """Extract 'owner/repo' from a GitHub issue URL."""
    # https://github.com/owner/repo/issues/123
    parts = html_url.split("/")
    try:
        idx = parts.index("github.com")
        return f"{parts[idx + 1]}/{parts[idx + 2]}"
    except (ValueError, IndexError):
        return ""


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_tags(labels: list[str], title: str) -> list[str]:
    """Build tags from issue labels and title keywords."""
    tags: set[str] = set()

    label_map = {
        "enhancement": "enhancement",
        "bug": "bug",
        "feature": "enhancement",
        "feature-request": "enhancement",
        "security": "security",
        "performance": "performance",
        "documentation": "docs",
    }

    for label in labels:
        lower = label.lower()
        mapped = label_map.get(lower)
        if mapped:
            tags.add(mapped)

    # Keyword scan on title
    keyword_map = {
        "ai": ["ai", "artificial intelligence"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "python": ["python"],
        "typescript": ["typescript"],
    }
    lower_title = title.lower()
    for tag, keywords in keyword_map.items():
        if any(kw in lower_title for kw in keywords):
            tags.add(tag)

    return sorted(tags)[:10]
