"""StackShare source adapter — developer tool adoption signals."""

from __future__ import annotations

import logging
import math
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://stackshare.io/api/v1"
_DEFAULT_STACKS = ["airbnb", "uber", "shopify"]
_DEFAULT_CATEGORIES = ["application-and-data", "utilities", "devops"]


class StackShareAdapter(SourceAdapter):
    """Fetch developer tool adoption signals from StackShare-style JSON APIs."""

    @property
    def name(self) -> str:
        return "stackshare"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return DEFAULT_BASE_URL

    @property
    def stacks(self) -> list[str]:
        return self._configured_terms("stacks", _DEFAULT_STACKS)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_tools: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for stack in self.stacks:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    self._stack_url(stack),
                    context=f"stack '{stack}'",
                    params={"limit": max(1, limit - len(signals))},
                )
                if data is None:
                    continue

                self._append_tool_signals(
                    signals,
                    data,
                    limit=limit,
                    seen_tools=seen_tools,
                    stack=stack,
                    category=None,
                )

            for category in self.categories:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    self._category_url(category),
                    context=f"category '{category}'",
                    params={"limit": max(1, limit - len(signals))},
                )
                if data is None:
                    continue

                self._append_tool_signals(
                    signals,
                    data,
                    limit=limit,
                    seen_tools=seen_tools,
                    stack=None,
                    category=category,
                )

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | list | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-stackshare-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch StackShare data for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    def _append_tool_signals(
        self,
        signals: list[Signal],
        data: dict | list,
        *,
        limit: int,
        seen_tools: set[str],
        stack: str | None,
        category: str | None,
    ) -> None:
        for entry in _extract_entries(data):
            if len(signals) >= limit:
                break

            try:
                tool = _tool_payload(entry)
                tool_name = _tool_name(tool)
                if tool_name is None:
                    continue

                dedupe_key = _dedupe_key(tool, tool_name)
                if dedupe_key in seen_tools:
                    continue

                signal = _tool_to_signal(
                    entry,
                    tool,
                    adapter_name=self.name,
                    base_url=self.base_url,
                    stack=stack,
                    category=category,
                )
                seen_tools.add(dedupe_key)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse StackShare tool entry: %s", self.name, e)

    def _stack_url(self, stack: str) -> str:
        return f"{self.base_url}/stacks/{quote(stack, safe='')}"

    def _category_url(self, category: str) -> str:
        return f"{self.base_url}/categories/{quote(category, safe='')}"


def _tool_to_signal(
    entry: dict,
    tool: dict,
    *,
    adapter_name: str,
    base_url: str,
    stack: str | None,
    category: str | None,
) -> Signal:
    tool_name = _tool_name(tool) or ""
    description = _string_or_none(
        tool.get("description")
        or tool.get("summary")
        or tool.get("tagline")
        or entry.get("description")
    ) or tool_name
    parsed_category = _category_name(tool, entry) or category
    source_url = _source_url(tool, entry, base_url, tool_name)
    company_count = _metric(entry, tool, _COMPANY_COUNT_KEYS) or 0
    user_count = _metric(entry, tool, _USER_COUNT_KEYS) or 0
    alternatives = _extract_alternatives(tool, entry)
    tags = _build_tags(
        category=parsed_category,
        stack=stack,
        configured_category=category,
        alternatives=alternatives,
    )

    metadata = {
        "tool_name": tool_name,
        "description": description,
        "category": parsed_category,
        "company_adoption_count": company_count,
        "user_adoption_count": user_count,
        "alternatives": alternatives,
        "source_url": source_url,
        "stack": stack,
        "configured_category": category,
        "slug": _string_or_none(tool.get("slug") or entry.get("slug")),
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=tool_name,
        content=description[:500],
        url=source_url,
        tags=tags,
        credibility=_credibility(
            company_adoption_count=company_count,
            user_adoption_count=user_count,
            alternatives=alternatives,
        ),
        metadata=metadata,
    )


def _extract_entries(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict):
        values = (
            data.get("tools")
            or data.get("services")
            or data.get("technologies")
            or data.get("stack_tools")
            or data.get("items")
            or data.get("results")
            or data.get("data")
            or []
        )
    else:
        values = []

    return [value for value in values if isinstance(value, dict)]


def _tool_payload(entry: dict) -> dict:
    for key in ("tool", "service", "technology", "software"):
        value = entry.get(key)
        if isinstance(value, dict):
            return value
    return entry


def _tool_name(tool: dict) -> str | None:
    return _string_or_none(tool.get("name") or tool.get("title") or tool.get("tool_name"))


def _dedupe_key(tool: dict, tool_name: str) -> str:
    slug = _string_or_none(tool.get("slug") or tool.get("id"))
    return (slug or tool_name).strip().lower()


def _category_name(tool: dict, entry: dict) -> str | None:
    for payload in (tool, entry):
        value = payload.get("category") or payload.get("layer")
        if isinstance(value, dict):
            category = _string_or_none(value.get("name") or value.get("slug") or value.get("title"))
            if category:
                return category
        elif isinstance(value, str) and value.strip():
            return value.strip()

        categories = payload.get("categories")
        if isinstance(categories, list) and categories:
            first = categories[0]
            if isinstance(first, str):
                return first.strip() or None
            if isinstance(first, dict):
                category = _string_or_none(first.get("name") or first.get("slug") or first.get("title"))
                if category:
                    return category
    return None


def _source_url(tool: dict, entry: dict, base_url: str, tool_name: str) -> str:
    explicit = _string_or_none(
        tool.get("url")
        or tool.get("stackshare_url")
        or tool.get("stackshareUrl")
        or entry.get("url")
        or entry.get("stackshare_url")
        or entry.get("stackshareUrl")
    )
    if explicit:
        return explicit

    slug = _string_or_none(tool.get("slug") or entry.get("slug"))
    if slug:
        return f"https://stackshare.io/{quote(slug, safe='')}"

    return f"{base_url}/tools/{quote(tool_name.lower().replace(' ', '-'), safe='')}"


_COMPANY_COUNT_KEYS = {
    "company_count",
    "companyCount",
    "companies_count",
    "companiesCount",
    "stacks_count",
    "stack_count",
    "stackCount",
    "stacksCount",
    "stackshare_stacks_count",
}
_USER_COUNT_KEYS = {
    "user_count",
    "userCount",
    "users_count",
    "usersCount",
    "followers",
    "follower_count",
    "votes",
    "votes_count",
    "likes",
}


def _metric(entry: dict, tool: dict, keys: set[str]) -> int | None:
    for payload in (tool, entry, tool.get("metrics"), entry.get("metrics"), tool.get("stats"), entry.get("stats")):
        value = _find_metric(payload, keys)
        if value is not None:
            return value
    return None


def _find_metric(value: object, keys: set[str]) -> int | None:
    if not isinstance(value, dict):
        return None

    for key, item in value.items():
        if key in keys:
            metric = _int_or_none(item)
            if metric is not None:
                return metric

    for item in value.values():
        if isinstance(item, dict):
            metric = _find_metric(item, keys)
            if metric is not None:
                return metric
    return None


def _extract_alternatives(tool: dict, entry: dict) -> list[str]:
    values: list[object] = []
    for payload in (tool, entry):
        raw = payload.get("alternatives") or payload.get("alternative_tools") or payload.get("similar_tools")
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str):
            values.extend(part.strip() for part in raw.split(","))

    alternatives: list[str] = []
    for value in values:
        if isinstance(value, str):
            alternatives.append(value)
        elif isinstance(value, dict):
            name = _string_or_none(value.get("name") or value.get("title") or value.get("slug"))
            if name:
                alternatives.append(name)

    return _dedupe(alternatives)[:10]


def _build_tags(
    *,
    category: str | None,
    stack: str | None,
    configured_category: str | None,
    alternatives: list[str],
) -> list[str]:
    tags = []
    if category:
        tags.append(category)
    if stack:
        tags.append(stack)
    if configured_category:
        tags.append(configured_category)
    tags.extend(alternatives[:3])
    return _dedupe(tags)[:10]


def _credibility(
    *,
    company_adoption_count: int,
    user_adoption_count: int,
    alternatives: list[str] | None = None,
) -> float:
    if company_adoption_count <= 0 and user_adoption_count <= 0:
        return 0.4

    company_score = min(math.log10(company_adoption_count + 1) / 5, 0.4)
    user_score = min(math.log10(user_adoption_count + 1) / 6, 0.3)
    alternative_score = 0.05 if alternatives else 0.0
    return min(round(0.25 + company_score + user_score + alternative_score, 3), 1.0)


def _int_or_none(value: object) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


StackshareAdapter = StackShareAdapter
