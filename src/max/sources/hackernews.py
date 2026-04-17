"""HackerNews source adapter — top/new stories from HN API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "hackernews"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def filter_keywords(self) -> list[str]:
        """Optional post-fetch keyword filter. Empty means no filtering."""
        return self._config.get("filter_keywords", [])

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        # Fetch extra stories when filtering to compensate for filtered-out results
        keywords = self.filter_keywords
        fetch_count = limit * 3 if keywords else limit

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await fetch_with_retry(
                f"{HN_API}/topstories.json", client, adapter_name=self.name,
            )
            try:
                story_ids = resp.json()[:fetch_count]
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(
                    "%s: failed to parse top stories JSON: %s",
                    self.name,
                    e,
                    exc_info=True,
                )
                raise SourceParseError(
                    f"failed to parse top stories JSON: {e}",
                    adapter_name=self.name,
                ) from e

            signals: list[Signal] = []
            for story_id in story_ids:
                try:
                    item_resp = await fetch_with_retry(
                        f"{HN_API}/item/{story_id}.json", client, adapter_name=self.name,
                    )
                except AdapterFetchError:
                    continue

                try:
                    item = item_resp.json()
                except (ValueError, KeyError, TypeError):
                    # Parse error for this item — log and continue with next item
                    logger.warning(
                        "%s: failed to parse item JSON for story %s",
                        self.name,
                        story_id,
                        exc_info=True,
                    )
                    continue

                if not item or item.get("type") != "story":
                    continue

                title = item.get("title", "")
                url = item.get("url", f"https://news.ycombinator.com/item?id={story_id}")

                # Compute credibility from score
                score = item.get("score", 0)
                credibility = min(score / 500, 1.0)

                # Apply keyword filter if configured
                if keywords:
                    lower_title = title.lower()
                    if not any(kw.lower() in lower_title for kw in keywords):
                        continue

                signals.append(
                    Signal(
                        source_type=SignalSourceType.FORUM,
                        source_adapter=self.name,
                        title=title,
                        content=title,  # HN stories are link-only; title is the signal
                        url=url,
                        author=item.get("by"),
                        published_at=datetime.fromtimestamp(
                            item.get("time", 0), tz=timezone.utc
                        ),
                        tags=_extract_tags(title),
                        credibility=credibility,
                        metadata={
                            "hn_id": story_id,
                            "score": score,
                            "descendants": item.get("descendants", 0),
                        },
                    )
                )

                if len(signals) >= limit:
                    break

            return signals[:limit]


def _extract_tags(title: str) -> list[str]:
    """Extract rough topic tags from title keywords."""
    keywords = {
        "ai": ["ai", "llm", "gpt", "claude", "machine learning", "ml"],
        "mcp": ["mcp", "model context protocol"],
        "agent": ["agent", "agentic"],
        "rust": ["rust"],
        "python": ["python"],
        "typescript": ["typescript", "node", "deno", "bun"],
        "security": ["security", "vulnerability", "cve"],
        "devtools": ["developer", "devtools", "ide", "editor", "vscode"],
        "open_source": ["open source", "oss", "github"],
        "startup": ["startup", "yc", "funding", "raised"],
    }
    lower = title.lower()
    return [tag for tag, terms in keywords.items() if any(t in lower for t in terms)]
