"""GitHub Marketplace Actions source adapter."""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterCircuitOpenError, AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API_SEARCH_REPOSITORIES = "https://api.github.com/search/repositories"
GITHUB_MARKETPLACE_ACTIONS_URL = "https://github.com/marketplace/actions"

_DEFAULT_QUERIES = ["ai", "agent", "mcp", "testing", "deployment"]
_ACTION_TOPIC = "github-action"


class GitHubMarketplaceActionsAdapter(SourceAdapter):
    """Fetch GitHub Marketplace Action adoption signals."""

    @property
    def name(self) -> str:
        return "github_marketplace_actions"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKETPLACE.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return _string_list(self._config.get("categories"))

    @property
    def max_results(self) -> int | None:
        return _positive_int_or_none(self._config.get("max_results"))

    @property
    def min_stars(self) -> int:
        return max(_int_or_none(self._config.get("min_stars")) or 0, 0)

    @property
    def max_age_days(self) -> int | None:
        return _positive_int_or_none(self._config.get("max_age_days"))

    @property
    def token(self) -> str | None:
        configured = _string_or_none(
            self._config.get("github_token") or self._config.get("token")
        )
        if configured:
            return configured

        token_env = _string_or_none(self._config.get("token_env"))
        if token_env:
            return _string_or_none(os.getenv(token_env))
        return None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.max_results) if self.max_results is not None else limit
        if effective_limit <= 0:
            return []

        signals: list[Signal] = []
        seen_actions: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for search_query, category in self._search_specs():
                if len(signals) >= effective_limit:
                    break

                data = await self._fetch_json(
                    client,
                    context=_context(search_query=search_query, category=category),
                    params={
                        "q": self._github_search_query(search_query, category),
                        "sort": "stars",
                        "order": "desc",
                        "per_page": min(100, max(1, effective_limit - len(signals))),
                    },
                )
                if data is None:
                    continue

                self._append_action_signals(
                    signals,
                    _extract_action_rows(data),
                    limit=effective_limit,
                    seen_actions=seen_actions,
                    search_query=search_query,
                    category_query=category,
                )

        return signals[:effective_limit]

    def _search_specs(self) -> list[tuple[str | None, str | None]]:
        specs: list[tuple[str | None, str | None]] = []
        for query in self.queries:
            specs.append((query, None))
        for category in self.categories:
            specs.append((None, category))
        return specs or [(None, None)]

    def _github_search_query(self, search_query: str | None, category: str | None) -> str:
        parts = [f"topic:{_ACTION_TOPIC}"]
        if search_query:
            parts.append(search_query)
        if category:
            parts.append(f"topic:{_topic_slug(category)}")
        if self.min_stars > 0:
            parts.append(f"stars:>={self.min_stars}")
        if self.max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
            parts.append(f"pushed:>={cutoff.date().isoformat()}")
        return " ".join(parts)

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | list | None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "max-github-marketplace-actions-adapter/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            resp = await fetch_with_retry(
                GITHUB_API_SEARCH_REPOSITORIES,
                client,
                adapter_name=self.name,
                params=params,
                headers=headers,
            )
            data = resp.json()
            return data if isinstance(data, (dict, list)) else None
        except (AdapterCircuitOpenError, AdapterFetchError) as e:
            logger.warning(
                "%s: failed to fetch GitHub Marketplace Actions data for %s: %s",
                self.name,
                context,
                e,
            )
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    def _append_action_signals(
        self,
        signals: list[Signal],
        actions: list[dict],
        *,
        limit: int,
        seen_actions: set[str],
        search_query: str | None,
        category_query: str | None,
    ) -> None:
        for action in actions:
            if len(signals) >= limit:
                break

            try:
                normalized = _action_payload(action)
                identity = _action_identity(normalized)
                if identity is None or identity in seen_actions:
                    continue
                if not _matches_filters(
                    normalized,
                    categories=self.categories,
                    min_stars=self.min_stars,
                    max_age_days=self.max_age_days,
                ):
                    continue

                signals.append(
                    _action_to_signal(
                        normalized,
                        adapter_name=self.name,
                        search_query=search_query,
                        category_query=category_query,
                    )
                )
                seen_actions.add(identity)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "%s: failed to parse GitHub Marketplace Action object: %s",
                    self.name,
                    e,
                )


def _extract_action_rows(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("items", "actions", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _action_payload(value: dict) -> dict:
    nested = value.get("repository")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key, item in value.items():
            if key != "repository" and key not in merged:
                merged[key] = item
        return merged
    return value


def _action_identity(action: dict) -> str | None:
    full_name = _string_or_none(action.get("full_name") or action.get("fullName"))
    if full_name:
        return full_name.lower()

    owner = _owner_login(action)
    name = _string_or_none(action.get("name"))
    if owner and name:
        return f"{owner}/{name}".lower()
    return None


def _action_to_signal(
    action: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    category_query: str | None,
) -> Signal:
    identity = _action_identity(action)
    if identity is None:
        raise ValueError("action missing repository identity")

    display_name = _string_or_none(
        action.get("marketplace_name")
        or action.get("marketplaceName")
        or action.get("display_name")
        or action.get("displayName")
        or action.get("name")
    )
    if display_name is None:
        raise ValueError("action missing name")

    publisher = _string_or_none(action.get("publisher") or action.get("owner_name")) or _owner_login(action)
    description = _string_or_none(
        action.get("description") or action.get("short_description") or action.get("shortDescription")
    )
    stars = _int_or_none(
        action.get("stargazers_count")
        or action.get("stars")
        or action.get("star_count")
        or action.get("starCount")
    )
    installs = _int_or_none(
        action.get("install_count")
        or action.get("installCount")
        or action.get("installs")
        or action.get("usage_count")
        or action.get("usageCount")
    )
    categories = _action_categories(action)
    topics = _string_list(action.get("topics"))
    language = _string_or_none(action.get("language"))
    published_at = _parse_datetime(
        action.get("published_at")
        or action.get("publishedAt")
        or action.get("created_at")
        or action.get("createdAt")
    )
    updated_at = _parse_datetime(
        action.get("updated_at")
        or action.get("updatedAt")
        or action.get("pushed_at")
        or action.get("pushedAt")
    )
    source_url = _source_url(action, identity=identity)
    title = display_name if "/" in display_name else f"{publisher}/{display_name}" if publisher else display_name
    content = _content(
        description=description or title,
        installs=installs,
        stars=stars,
        categories=categories,
        publisher=publisher,
    )

    metadata = {
        "repository": identity,
        "publisher": publisher,
        "name": _string_or_none(action.get("name")),
        "marketplace_name": display_name,
        "install_count": installs,
        "stars": stars,
        "watchers": _int_or_none(action.get("watchers_count") or action.get("watchers")),
        "forks": _int_or_none(action.get("forks_count") or action.get("forks")),
        "open_issues": _int_or_none(action.get("open_issues_count") or action.get("open_issues")),
        "category": categories[0] if categories else None,
        "categories": categories,
        "topics": topics,
        "language": language,
        "license": _license_name(action.get("license")),
        "published_at": published_at.isoformat() if published_at is not None else None,
        "updated_at": updated_at.isoformat() if updated_at is not None else None,
        "source_url": source_url,
        "search_query": search_query,
        "category_query": category_query,
    }

    return Signal(
        id=f"{adapter_name}:{identity}",
        source_type=SignalSourceType.MARKETPLACE,
        source_adapter=adapter_name,
        title=title,
        content=content[:500],
        url=source_url,
        author=publisher,
        published_at=published_at or updated_at,
        tags=_build_tags(categories=categories, topics=topics, search_query=search_query),
        credibility=_credibility(stars=stars, installs=installs),
        metadata=metadata,
    )


def _matches_filters(
    action: dict,
    *,
    categories: list[str],
    min_stars: int,
    max_age_days: int | None,
) -> bool:
    stars = _int_or_none(
        action.get("stargazers_count")
        or action.get("stars")
        or action.get("star_count")
        or action.get("starCount")
    )
    if min_stars and (stars or 0) < min_stars:
        return False

    if categories:
        category_terms = {_normalize_term(item) for item in _action_categories(action)}
        topic_terms = {_normalize_term(item) for item in _string_list(action.get("topics"))}
        filters = {_normalize_term(item) for item in categories}
        if not (filters & category_terms or filters & topic_terms):
            return False

    if max_age_days is not None:
        updated_at = _parse_datetime(
            action.get("updated_at")
            or action.get("updatedAt")
            or action.get("pushed_at")
            or action.get("pushedAt")
            or action.get("published_at")
            or action.get("publishedAt")
        )
        if updated_at is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            if updated_at < cutoff:
                return False
    return True


def _action_categories(action: dict) -> list[str]:
    categories = _string_list(action.get("categories"))
    category = _string_or_none(
        action.get("category")
        or action.get("primary_category")
        or action.get("primaryCategory")
        or action.get("marketplace_category")
        or action.get("marketplaceCategory")
    )
    if category:
        categories.insert(0, category)
    return _dedupe_strings(categories)


def _content(
    *,
    description: str,
    installs: int | None,
    stars: int | None,
    categories: list[str],
    publisher: str | None,
) -> str:
    details: list[str] = []
    if installs is not None:
        details.append(f"{installs:,} installs")
    if stars is not None:
        details.append(f"{stars:,} stars")
    if categories:
        details.append(f"category: {categories[0]}")
    if publisher:
        details.append(f"publisher: {publisher}")
    return f"{description} ({'; '.join(details)})" if details else description


def _source_url(action: dict, *, identity: str) -> str:
    for key in ("html_url", "htmlUrl", "url", "marketplace_url", "marketplaceUrl"):
        value = _string_or_none(action.get(key))
        if value and value.startswith("http"):
            return value
    owner, name = identity.split("/", 1)
    return f"{GITHUB_MARKETPLACE_ACTIONS_URL}/{quote(owner, safe='')}/{quote(name, safe='')}"


def _owner_login(action: dict) -> str | None:
    owner = action.get("owner")
    if isinstance(owner, dict):
        return _string_or_none(owner.get("login") or owner.get("name"))
    return _string_or_none(action.get("owner") or action.get("publisher_login"))


def _license_name(value: object) -> str | None:
    if isinstance(value, dict):
        return _string_or_none(value.get("spdx_id") or value.get("key") or value.get("name"))
    return _string_or_none(value)


def _build_tags(
    *,
    categories: list[str],
    topics: list[str],
    search_query: str | None,
) -> list[str]:
    values = [*categories, *topics]
    if search_query:
        values.append(search_query)
    return _dedupe_strings(values)[:10]


def _credibility(*, stars: int | None, installs: int | None) -> float:
    adoption = max(stars or 0, installs or 0)
    adoption_score = min(math.log10(adoption + 1) / 7, 0.75)
    return min(round(0.2 + adoption_score, 3), 1.0)


def _context(*, search_query: str | None, category: str | None) -> str:
    if search_query:
        return f"query '{search_query}'"
    if category:
        return f"category '{category}'"
    return "default search"


def _topic_slug(value: str) -> str:
    return _normalize_term(value).replace(" ", "-")


def _normalize_term(value: str) -> str:
    return " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []
    return _dedupe_strings(values)


def _dedupe_strings(values: list[object]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _positive_int_or_none(value: object) -> int | None:
    parsed = _int_or_none(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
