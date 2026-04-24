"""Mastodon source adapter -- public Fediverse timeline signals."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
    SourceAdapter,
    fetch_with_retry,
)
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_INSTANCES = ["mastodon.social"]
_DEFAULT_HASHTAGS = ["opensource", "devtools", "python", "ai"]
_DEFAULT_ACCESS_TOKEN_ENV = "MASTODON_ACCESS_TOKEN"


class MastodonAdapter(SourceAdapter):
    """Fetch public Mastodon hashtag and account timelines."""

    @property
    def name(self) -> str:
        return "mastodon"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def instances(self) -> list[str]:
        return _normalize_strings(self._config.get("instances", _DEFAULT_INSTANCES))

    @property
    def hashtags(self) -> list[str]:
        return [_normalize_hashtag(tag) for tag in self._configured_terms("hashtags", _DEFAULT_HASHTAGS)]

    @property
    def accounts(self) -> list[str]:
        return _normalize_strings(self._config.get("accounts", []))

    @property
    def exclude_reblogs(self) -> bool:
        return bool(self._config.get("exclude_reblogs", True))

    @property
    def min_favourites(self) -> int:
        return _int_or_zero(self._config.get("min_favourites"))

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

    @property
    def access_token_env(self) -> str:
        value = self._config.get("access_token_env", _DEFAULT_ACCESS_TOKEN_ENV)
        return value if isinstance(value, str) and value.strip() else _DEFAULT_ACCESS_TOKEN_ENV

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen_status_ids: set[tuple[str, str]] = set()
        headers = {
            "Accept": "application/json",
            "User-Agent": "max-mastodon-adapter/0.1",
        }
        token = os.environ.get(self.access_token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            for instance in self.instances:
                if len(signals) >= limit:
                    break
                await self._fetch_instance(
                    client,
                    instance=instance,
                    signals=signals,
                    seen_status_ids=seen_status_ids,
                    limit=limit,
                )

        return signals[:limit]

    async def _fetch_instance(
        self,
        client: httpx.AsyncClient,
        *,
        instance: str,
        signals: list[Signal],
        seen_status_ids: set[tuple[str, str]],
        limit: int,
    ) -> None:
        base_url = _instance_base_url(instance)
        per_source = _per_source_limit(limit, len(self.hashtags) + len(self.accounts))

        for hashtag in self.hashtags:
            if len(signals) >= limit:
                return
            statuses = await self._fetch_statuses(
                client,
                url=f"{base_url}/api/v1/timelines/tag/{quote(hashtag, safe='')}",
                params={"limit": per_source},
                context={"instance": instance, "hashtag": hashtag},
            )
            self._append_statuses(
                signals,
                statuses,
                instance=instance,
                timeline="hashtag",
                query=hashtag,
                seen_status_ids=seen_status_ids,
                limit=limit,
            )

        for account in self.accounts:
            if len(signals) >= limit:
                return
            account_id = await self._resolve_account_id(client, base_url=base_url, account=account)
            if account_id is None:
                continue
            statuses = await self._fetch_statuses(
                client,
                url=f"{base_url}/api/v1/accounts/{quote(account_id, safe='')}/statuses",
                params={"limit": per_source, "exclude_reblogs": self.exclude_reblogs},
                context={"instance": instance, "account": account},
            )
            self._append_statuses(
                signals,
                statuses,
                instance=instance,
                timeline="account",
                query=account,
                seen_status_ids=seen_status_ids,
                limit=limit,
            )

    async def _resolve_account_id(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        account: str,
    ) -> str | None:
        if account.isdigit():
            return account

        lookup_account = account.strip().lstrip("@")
        if "@" in lookup_account:
            lookup_account = lookup_account.split("@", 1)[0]

        try:
            response = await fetch_with_retry(
                f"{base_url}/api/v1/accounts/lookup",
                client,
                adapter_name=self.name,
                params={"acct": lookup_account},
            )
            data = response.json()
        except (AdapterRateLimitError, AdapterCircuitOpenError):
            raise
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning("Mastodon account lookup failed for %s", account, exc_info=True)
            return None

        if not isinstance(data, dict):
            return None
        account_id = data.get("id")
        return str(account_id) if account_id else None

    async def _fetch_statuses(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict,
        context: dict[str, str],
    ) -> list[dict]:
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
            )
            data = response.json()
        except (AdapterRateLimitError, AdapterCircuitOpenError):
            raise
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning("Mastodon fetch failed for %s", context, exc_info=True)
            return []

        if not isinstance(data, list):
            logger.warning("Mastodon response was not a list for %s", context)
            return []
        return [item for item in data if isinstance(item, dict)]

    def _append_statuses(
        self,
        signals: list[Signal],
        statuses: list[dict],
        *,
        instance: str,
        timeline: str,
        query: str,
        seen_status_ids: set[tuple[str, str]],
        limit: int,
    ) -> None:
        for status in statuses:
            if len(signals) >= limit:
                break
            status_id = _status_id(status)
            if status_id is None:
                continue
            dedupe_key = (instance, status_id)
            if dedupe_key in seen_status_ids:
                continue
            signal = self._status_to_signal(status, instance=instance, timeline=timeline, query=query)
            if signal is None:
                continue
            seen_status_ids.add(dedupe_key)
            signals.append(signal)

    def _status_to_signal(
        self,
        status: dict,
        *,
        instance: str,
        timeline: str,
        query: str,
    ) -> Signal | None:
        if self.exclude_reblogs and status.get("reblog") is not None:
            return None

        favourites = _int_or_zero(status.get("favourites_count"))
        if favourites < self.min_favourites:
            return None

        published_at = _parse_dt(status.get("created_at"))
        if self._is_too_old(published_at):
            return None

        content = _html_to_text(status.get("content"))
        if not content:
            content = _html_to_text(_nested_value(status, "spoiler_text")) or _status_url(status)
        if not content:
            return None

        account = status.get("account") if isinstance(status.get("account"), dict) else {}
        account_handle = _account_handle(account, instance)
        hashtags = _extract_hashtags(status)
        status_id = _status_id(status)
        if status_id is None:
            return None

        reblogs = _int_or_zero(status.get("reblogs_count"))
        replies = _int_or_zero(status.get("replies_count"))
        sensitive = bool(status.get("sensitive", False))

        return Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter=self.name,
            title=_title_from_text(content),
            content=content[:1000],
            url=_status_url(status),
            author=account_handle,
            published_at=published_at,
            tags=_build_tags(timeline=timeline, query=query, hashtags=hashtags),
            credibility=_credibility(favourites=favourites, reblogs=reblogs, replies=replies),
            metadata={
                "instance": instance,
                "status_id": status_id,
                "account_handle": account_handle,
                "favourites": favourites,
                "reblogs": reblogs,
                "replies": replies,
                "language": _str_or_none(status.get("language")),
                "hashtags": hashtags,
                "sensitive": sensitive,
                "timeline": timeline,
                "query": query,
                "uri": _str_or_none(status.get("uri")),
                "url": _status_url(status),
            },
        )

    def _is_too_old(self, published_at: datetime | None) -> bool:
        if self.max_age_days is None or published_at is None:
            return False
        compare_at = published_at
        if compare_at.tzinfo is None:
            compare_at = compare_at.replace(tzinfo=timezone.utc)
        return compare_at < datetime.now(timezone.utc) - timedelta(days=self.max_age_days)


def _instance_base_url(instance: str) -> str:
    normalized = instance.strip().rstrip("/")
    if not normalized:
        normalized = _DEFAULT_INSTANCES[0]
    if normalized.startswith(("http://", "https://")):
        return normalized
    return f"https://{normalized}"


def _per_source_limit(limit: int, source_count: int) -> int:
    return min(max(limit // max(source_count, 1), 5), 40)


def _normalize_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            continue
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _normalize_hashtag(value: str) -> str:
    return value.strip().lstrip("#")


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _status_id(status: dict) -> str | None:
    status_id = status.get("id")
    return str(status_id) if status_id else None


def _status_url(status: dict) -> str:
    return _str_or_none(status.get("url")) or _str_or_none(status.get("uri")) or ""


def _account_handle(account: dict, instance: str) -> str | None:
    acct = _str_or_none(account.get("acct"))
    if acct:
        return acct if "@" in acct else f"{acct}@{instance}"
    username = _str_or_none(account.get("username"))
    return f"{username}@{instance}" if username else None


def _extract_hashtags(status: dict) -> list[str]:
    tags = status.get("tags")
    if not isinstance(tags, list):
        return []

    seen: set[str] = set()
    hashtags: list[str] = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        name = _str_or_none(tag.get("name"))
        if not name:
            continue
        normalized = _tagify(name)
        if normalized and normalized not in seen:
            seen.add(normalized)
            hashtags.append(normalized)
    return hashtags


def _build_tags(*, timeline: str, query: str, hashtags: list[str]) -> list[str]:
    tags = {"mastodon", "fediverse", timeline}
    query_tag = _tagify(query)
    if query_tag:
        tags.add(query_tag)
    tags.update(tag for tag in hashtags if tag)
    return sorted(tags)[:10]


def _credibility(*, favourites: int, reblogs: int, replies: int) -> float:
    score = (favourites * 2) + (reblogs * 3) + replies
    return min(0.25 + (score / 100.0), 1.0)


def _title_from_text(text: str) -> str:
    line = " ".join(text.split())
    return line[:117] + "..." if len(line) > 120 else line


def _int_or_zero(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _str_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _nested_value(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _tagify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "li"}:
            self.parts.append(" ")


def _html_to_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())
