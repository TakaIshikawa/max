"""StackOverflow source adapter — developer pain-point signals via Stack Exchange API."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

SE_API = "https://api.stackexchange.com/2.3"

_DEFAULT_TAGS = ["langchain", "openai", "llm", "mcp", "ai-agent"]


def _get_api_key() -> str | None:
    """Resolve Stack Exchange API key from env or vault."""
    key = os.environ.get("STACKEXCHANGE_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["vault", "get", "stackexchange/key"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _extract_tags(title: str, so_tags: list[str]) -> list[str]:
    """Build signal tags from SO question tags and title keywords."""
    tags: set[str] = set()
    for t in so_tags[:10]:
        tags.add(t.lower())
    kw_map = {
        "agent": "agent", "llm": "llm", "mcp": "mcp",
        "langchain": "langchain", "openai": "openai",
        "anthropic": "anthropic", "claude": "claude",
        "rag": "rag", "embedding": "embedding", "vector": "vector",
    }
    title_lower = title.lower()
    for keyword, tag in kw_map.items():
        if keyword in title_lower:
            tags.add(tag)
    tags.add("stackoverflow")
    return sorted(tags)[:10]


def _strip_html(text: str) -> str:
    """Strip HTML tags from SO question bodies."""
    import re
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


class StackOverflowAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "stackoverflow"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def tags(self) -> list[str]:
        return self._config.get("tags", _DEFAULT_TAGS)

    @property
    def min_score(self) -> int:
        return self._config.get("min_score", 5)

    @property
    def unanswered_only(self) -> bool:
        return self._config.get("unanswered_only", False)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_ids: set[int] = set()
        api_key = _get_api_key()

        # Split tags into batches of 5 (SE API supports semicolon-separated OR)
        tag_batches = [
            self.tags[i:i + 5] for i in range(0, len(self.tags), 5)
        ]

        async with httpx.AsyncClient(timeout=30) as client:
            for batch in tag_batches:
                if len(signals) >= limit:
                    break

                params: dict = {
                    "tagged": ";".join(batch),
                    "sort": "votes",
                    "order": "desc",
                    "site": "stackoverflow",
                    "filter": "withbody",
                    "pagesize": min(limit, 50),
                    "min": self.min_score,
                }
                if self.unanswered_only:
                    params["accepted"] = "False"
                if api_key:
                    params["key"] = api_key

                try:
                    resp = await fetch_with_retry(
                        f"{SE_API}/questions",
                        client,
                        adapter_name=self.name,
                        params=params,
                    )
                    data = resp.json()
                except Exception:
                    logger.warning("StackOverflow fetch failed for tags: %s", batch, exc_info=True)
                    continue

                quota = data.get("quota_remaining")
                if quota is not None:
                    logger.debug("SE API quota remaining: %d", quota)

                for item in data.get("items", []):
                    qid = item.get("question_id")
                    if qid in seen_ids:
                        continue
                    seen_ids.add(qid)

                    score = item.get("score", 0)
                    body = _strip_html(item.get("body", ""))[:1000]

                    signals.append(Signal(
                        source_type=SignalSourceType.FORUM,
                        source_adapter=self.name,
                        title=item.get("title", ""),
                        content=body,
                        url=item.get("link", ""),
                        author=(item.get("owner") or {}).get("display_name"),
                        published_at=datetime.fromtimestamp(
                            item.get("creation_date", 0), tz=timezone.utc,
                        ),
                        tags=_extract_tags(item.get("title", ""), item.get("tags", [])),
                        credibility=min(score / 200, 1.0),
                        metadata={
                            "question_id": qid,
                            "score": score,
                            "view_count": item.get("view_count", 0),
                            "answer_count": item.get("answer_count", 0),
                            "is_answered": item.get("is_answered", False),
                        },
                    ))

                    if len(signals) >= limit:
                        break

        return signals[:limit]
