"""Stack Exchange source adapter — cross-site technical question signals."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urlsplit, urlunsplit

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.stackoverflow import _get_api_key
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

SE_API = "https://api.stackexchange.com/2.3"

_DEFAULT_SITES = ["stackoverflow", "serverfault", "superuser"]
_DEFAULT_TAGS = ["ai", "llm", "devops", "security", "data-science"]
_BODY_EXCERPT_CHARS = 1000


class StackExchangeAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "stackexchange"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def sites(self) -> list[str]:
        return self._configured_terms("sites", _DEFAULT_SITES)

    @property
    def tags(self) -> list[str]:
        default = [] if self._config.get("queries") is not None else _DEFAULT_TAGS
        return self._configured_terms("tags", default)

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", [])

    @property
    def min_score(self) -> int:
        return _positive_int(self._config.get("min_score"), default=0)

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        if value is None or isinstance(value, bool):
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        api_key = _get_api_key()
        fromdate = self._fromdate()

        async with httpx.AsyncClient(timeout=30) as client:
            for site in self.sites:
                if len(signals) >= limit:
                    break
                await self._fetch_site(
                    client,
                    site=site,
                    limit=limit,
                    api_key=api_key,
                    fromdate=fromdate,
                    signals=signals,
                    seen_ids=seen_ids,
                )

        return signals[:limit]

    async def _fetch_site(
        self,
        client: httpx.AsyncClient,
        *,
        site: str,
        limit: int,
        api_key: str | None,
        fromdate: int | None,
        signals: list[Signal],
        seen_ids: set[str],
    ) -> None:
        if self.queries:
            searches = [("query", query) for query in self.queries]
        else:
            searches = [("tags", ";".join(self.tags))]

        for mode, value in searches:
            if len(signals) >= limit:
                return
            await self._fetch_search(
                client,
                site=site,
                mode=mode,
                value=value,
                limit=limit,
                api_key=api_key,
                fromdate=fromdate,
                signals=signals,
                seen_ids=seen_ids,
            )

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        site: str,
        mode: str,
        value: str,
        limit: int,
        api_key: str | None,
        fromdate: int | None,
        signals: list[Signal],
        seen_ids: set[str],
    ) -> None:
        page = 1
        while len(signals) < limit:
            params: dict = {
                "site": site,
                "order": "desc",
                "sort": "creation",
                "filter": "withbody",
                "pagesize": min(max(limit - len(signals), 1), 100),
                "page": page,
            }
            if fromdate is not None:
                params["fromdate"] = fromdate
            if self.min_score > 0:
                params["min"] = self.min_score
            if api_key:
                params["key"] = api_key

            url = f"{SE_API}/questions"
            if mode == "query":
                url = f"{SE_API}/search/advanced"
                params["q"] = value
                if self.tags:
                    params["tagged"] = ";".join(self.tags)
            elif value:
                params["tagged"] = value

            try:
                resp = await fetch_with_retry(
                    url,
                    client,
                    adapter_name=self.name,
                    params=params,
                )
                data = resp.json()
            except Exception:
                logger.warning(
                    "Stack Exchange fetch failed for site=%s mode=%s value=%s",
                    site,
                    mode,
                    value,
                    exc_info=True,
                )
                return

            items = data.get("items", [])
            if not isinstance(items, list) or not items:
                return

            for item in items:
                signal = self._normalize_question(item, site=site)
                if signal is None or signal.id in seen_ids:
                    continue
                seen_ids.add(signal.id)
                signals.append(signal)
                if len(signals) >= limit:
                    return

            if not data.get("has_more"):
                return
            page += 1

    def _normalize_question(self, item: object, *, site: str) -> Signal | None:
        if not isinstance(item, dict):
            return None

        question_id = item.get("question_id")
        title = _string_or_none(item.get("title"))
        if question_id is None or not title:
            return None

        try:
            score = int(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        if score < self.min_score:
            return None

        published_at = _datetime_from_epoch(item.get("creation_date"))
        if self._is_too_old(published_at):
            return None

        site_name = _string_or_none(item.get("site")) or site
        link = _canonical_question_url(item.get("link"), site=site_name, question_id=question_id)
        body = _strip_html(_string_or_none(item.get("body")) or "")
        content = f"{title}\n\n{body[:_BODY_EXCERPT_CHARS]}".strip()
        question_tags = _string_list(item.get("tags"))

        return Signal(
            id=f"stackexchange:{site_name}:{question_id}",
            source_type=SignalSourceType.FORUM,
            source_adapter=self.name,
            title=title,
            content=content,
            url=link,
            author=((item.get("owner") or {}) if isinstance(item.get("owner"), dict) else {}).get(
                "display_name"
            ),
            published_at=published_at,
            tags=_extract_tags(site_name, title, question_tags),
            credibility=min(max(score, 0) / 200, 1.0),
            metadata={
                "site": site_name,
                "question_id": question_id,
                "score": score,
                "view_count": item.get("view_count", 0),
                "answer_count": item.get("answer_count", 0),
                "comment_count": item.get("comment_count", 0),
                "is_answered": item.get("is_answered", False),
                "tags": question_tags[:10],
            },
        )

    def _fromdate(self) -> int | None:
        if self.max_age_days is None:
            return None
        threshold = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        return int(threshold.timestamp())

    def _is_too_old(self, published_at: datetime | None) -> bool:
        if self.max_age_days is None or published_at is None:
            return False
        return published_at < datetime.now(timezone.utc) - timedelta(days=self.max_age_days)


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _datetime_from_epoch(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = unescape(value).strip()
    return stripped or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    tags = []
    for item in value:
        if isinstance(item, str) and item.strip():
            tags.append(unescape(item).strip().lower())
    return tags


def _strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", unescape(text))
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _extract_tags(site: str, title: str, question_tags: list[str]) -> list[str]:
    tags: list[str] = []
    for tag in [site, "stackexchange", *question_tags]:
        normalized = tag.strip().lower()
        if normalized and normalized not in tags:
            tags.append(normalized)

    title_lower = title.lower()
    for keyword in ("ai", "llm", "mcp", "devops", "security", "data", "python"):
        if keyword in title_lower and keyword not in tags:
            tags.append(keyword)
    return tags[:10]


def _canonical_question_url(link: object, *, site: str, question_id: object) -> str:
    if isinstance(link, str) and link.strip():
        parsed = urlsplit(unescape(link.strip()))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))

    host = _site_host(site)
    return f"https://{host}/questions/{question_id}"


def _site_host(site: str) -> str:
    special = {
        "askubuntu": "askubuntu.com",
        "mathoverflow": "mathoverflow.net",
        "serverfault": "serverfault.com",
        "stackapps": "stackapps.com",
        "stackoverflow": "stackoverflow.com",
        "superuser": "superuser.com",
    }
    return special.get(site, f"{site}.stackexchange.com")
