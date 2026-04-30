"""Hacker News Who Is Hiring adapter — monthly hiring threads."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"
ALGOLIA_API = "https://hn.algolia.com/api/v1/search"

_WHO_IS_HIRING_QUERY = 'Ask HN: Who is hiring?'
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_MONTH_RE = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")\s+(\d{4})\b",
    re.IGNORECASE,
)
_TECHNOLOGY_KEYWORDS = {
    "ai": (" ai ", " llm", "gpt", "claude", "machine learning", "ml"),
    "aws": ("aws",),
    "c++": ("c++",),
    "data": ("data", "analytics", "snowflake", "dbt"),
    "docker": ("docker", "container"),
    "go": (" golang", " go "),
    "java": ("java", "jvm", "kotlin", "scala"),
    "javascript": ("javascript", "node", "react", "vue", "svelte"),
    "kubernetes": ("kubernetes", "k8s"),
    "mobile": ("ios", "android", "react native"),
    "python": ("python", "django", "fastapi"),
    "rust": ("rust",),
    "security": ("security", "soc2", "compliance"),
    "typescript": ("typescript", " ts ", "next.js", "nestjs"),
}


class HackerNewsWhoIsHiringAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "hackernews_whoishiring"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def item_ids(self) -> list[int]:
        values = self._config.get("item_ids", [])
        item_ids: list[int] = []
        for value in values:
            try:
                item_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return item_ids

    @property
    def algolia_url(self) -> str:
        return str(self._config.get("algolia_url", ALGOLIA_API)).rstrip("/")

    @property
    def hn_api_url(self) -> str:
        return str(self._config.get("hn_api_url", HN_API)).rstrip("/")

    @property
    def max_threads(self) -> int:
        try:
            return max(1, int(self._config.get("max_threads", 3)))
        except (TypeError, ValueError):
            return 3

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            thread_ids = self.item_ids or await self._discover_thread_ids(client)
            signals: list[Signal] = []
            seen_comment_ids: set[int] = set()

            for thread_id in thread_ids[: self.max_threads]:
                try:
                    thread = await self._fetch_item(client, thread_id)
                except AdapterFetchError:
                    continue

                if not thread or thread.get("type") != "story":
                    continue

                thread_title = str(thread.get("title") or "")
                thread_month = _parse_thread_month(thread_title)
                comment_ids = [kid for kid in thread.get("kids", []) if isinstance(kid, int)]

                for comment_id in comment_ids:
                    if len(signals) >= limit:
                        return signals
                    if comment_id in seen_comment_ids:
                        continue
                    seen_comment_ids.add(comment_id)

                    try:
                        comment = await self._fetch_item(client, comment_id)
                    except AdapterFetchError:
                        continue

                    signal = _comment_to_signal(
                        comment,
                        thread_id=thread_id,
                        thread_title=thread_title,
                        thread_month=thread_month,
                        adapter_name=self.name,
                    )
                    if signal is not None:
                        signals.append(signal)

            return signals[:limit]

    async def _discover_thread_ids(self, client: httpx.AsyncClient) -> list[int]:
        response = await fetch_with_retry(
            self.algolia_url,
            client,
            adapter_name=self.name,
            params={
                "query": _WHO_IS_HIRING_QUERY,
                "tags": "story",
                "restrictSearchableAttributes": "title",
            },
        )

        try:
            payload = response.json()
        except (ValueError, TypeError) as e:
            logger.warning("%s: failed to parse Algolia response", self.name, exc_info=True)
            raise SourceParseError(
                f"failed to parse Algolia response: {e}",
                adapter_name=self.name,
            ) from e

        hits = payload.get("hits", []) if isinstance(payload, dict) else []
        thread_ids: list[int] = []
        seen: set[int] = set()
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            title = str(hit.get("title") or hit.get("story_title") or "")
            if "who is hiring" not in title.lower():
                continue
            raw_id = hit.get("objectID") or hit.get("story_id")
            try:
                thread_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if thread_id in seen:
                continue
            seen.add(thread_id)
            thread_ids.append(thread_id)
            if len(thread_ids) >= self.max_threads:
                break

        return thread_ids

    async def _fetch_item(self, client: httpx.AsyncClient, item_id: int) -> dict[str, Any] | None:
        response = await fetch_with_retry(
            f"{self.hn_api_url}/item/{item_id}.json",
            client,
            adapter_name=self.name,
        )
        try:
            item = response.json()
        except (ValueError, TypeError):
            logger.warning(
                "%s: failed to parse HN item JSON for %s",
                self.name,
                item_id,
                exc_info=True,
            )
            return None
        return item if isinstance(item, dict) else None


def _comment_to_signal(
    comment: dict[str, Any] | None,
    *,
    thread_id: int,
    thread_title: str,
    thread_month: str | None,
    adapter_name: str,
) -> Signal | None:
    if not comment or comment.get("type") != "comment":
        return None
    if comment.get("deleted") or comment.get("dead"):
        return None

    comment_id = comment.get("id")
    text = _clean_hn_text(str(comment.get("text") or ""))
    if not text:
        return None

    metadata = _extract_hiring_metadata(text)
    company = metadata.get("company")
    title = f"{company} hiring on Hacker News" if company else _truncate(text, 80)
    published_at = None
    if isinstance(comment.get("time"), int):
        published_at = datetime.fromtimestamp(comment["time"], tz=timezone.utc)

    metadata.update(
        {
            "hn_comment_id": comment_id,
            "hn_thread_id": thread_id,
            "thread_title": thread_title,
            "thread_month": thread_month,
            "signal_role": "market",
        }
    )

    return Signal(
        id=f"hackernews_whoishiring:{comment_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=text,
        url=f"https://news.ycombinator.com/item?id={comment_id}",
        author=comment.get("by"),
        published_at=published_at,
        tags=_build_tags(metadata),
        credibility=0.65,
        metadata=metadata,
    )


def _clean_hn_text(raw_text: str) -> str:
    text = re.sub(r"<p\s*/?>", "\n", raw_text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _parse_thread_month(title: str) -> str | None:
    match = _MONTH_RE.search(title)
    if not match:
        return None
    month = match.group(1).lower().capitalize()
    return f"{month} {match.group(2)}"


def _extract_hiring_metadata(text: str) -> dict[str, Any]:
    first_line = text.splitlines()[0]
    segments = [segment.strip(" -") for segment in re.split(r"\s+\|\s+", first_line) if segment.strip()]
    company = segments[0] if segments else None
    location = _find_location(segments)
    remote = _parse_remote(text)
    technologies = _extract_technologies(text)

    return {
        "company": company,
        "location": location,
        "remote": remote,
        "technologies": technologies,
    }


def _find_location(segments: list[str]) -> str | None:
    for segment in segments[1:]:
        lower = segment.lower()
        if lower == "remote" or "visa" in lower or "salary" in lower:
            continue
        if any(marker in segment for marker in [",", "/", "(", ")"]) or lower in {
            "nyc",
            "sf",
            "london",
            "berlin",
            "paris",
            "tokyo",
            "austin",
            "boston",
            "seattle",
            "new york",
            "san francisco",
        }:
            return segment
    return None


def _parse_remote(text: str) -> bool | None:
    lower = text.lower()
    if "no remote" in lower or "not remote" in lower or "onsite only" in lower:
        return False
    if "remote" in lower or "wfh" in lower or "work from home" in lower:
        return True
    return None


def _extract_technologies(text: str) -> list[str]:
    lower = f" {_WHITESPACE_RE.sub(' ', text.lower())} "
    technologies: list[str] = []
    for label, needles in _TECHNOLOGY_KEYWORDS.items():
        if any(needle in lower for needle in needles):
            technologies.append(label)
    return technologies


def _build_tags(metadata: dict[str, Any]) -> list[str]:
    tags = ["hackernews", "who-is-hiring", "hiring", "market-demand"]
    if metadata.get("remote") is True:
        tags.append("remote")
    tags.extend(metadata.get("technologies") or [])
    return tags


def _truncate(text: str, max_length: int) -> str:
    compact = _WHITESPACE_RE.sub(" ", text).strip()
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3].rstrip()}..."
