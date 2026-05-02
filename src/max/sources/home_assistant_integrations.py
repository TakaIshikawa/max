"""Home Assistant integrations source adapter -- local-first ecosystem signals."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

HOME_ASSISTANT_INTEGRATIONS_URL = "https://www.home-assistant.io/integrations.json"
HOME_ASSISTANT_INTEGRATION_WEB_URL = "https://www.home-assistant.io/integrations/{domain}/"

_DEFAULT_INTEGRATIONS: list[str] = []
_DEFAULT_CATEGORIES: list[str] = []


class HomeAssistantIntegrationsAdapter(SourceAdapter):
    """Fetch Home Assistant integration catalog metadata as registry signals."""

    @property
    def name(self) -> str:
        return "home_assistant_integrations"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def integrations_url(self) -> str:
        configured = self._config.get("integrations_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return HOME_ASSISTANT_INTEGRATIONS_URL

    @property
    def integrations(self) -> list[str]:
        configured = self._config.get("integrations", self._config.get("domains"))
        return _normalized_terms(configured, default=_DEFAULT_INTEGRATIONS)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def max_age_days(self) -> int | None:
        return _positive_int_or_none(self._config.get("max_age_days"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = max(limit, 0)
        if effective_limit == 0:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            payload = await self._fetch_payload(client)

        signals: list[Signal] = []
        seen: set[str] = set()
        cutoff = _cutoff(self.max_age_days)

        for item in payload:
            if len(signals) >= effective_limit:
                break

            domain = _integration_domain(item)
            if domain is None:
                continue

            identity = domain.lower()
            if identity in seen:
                continue

            if not _matches_filters(
                item,
                integrations=self.integrations,
                categories=self.categories,
            ):
                continue

            published_at = _integration_datetime(item)
            if cutoff is not None and published_at is not None and published_at < cutoff:
                continue

            try:
                signal = _integration_to_signal(
                    item,
                    adapter_name=self.name,
                    source_url=self.integrations_url,
                    published_at=published_at,
                )
            except (TypeError, ValueError) as e:
                logger.warning(
                    "%s: failed to parse Home Assistant integration record: %s",
                    self.name,
                    e,
                )
                continue

            seen.add(identity)
            signals.append(signal)

        return signals[:effective_limit]

    async def _fetch_payload(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await fetch_with_retry(
                self.integrations_url,
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-home-assistant-integrations-adapter/0.1"},
            )
            data = resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Home Assistant integrations: %s", self.name, e)
            return []
        except httpx.RequestError as e:
            logger.warning("%s: request failed for Home Assistant integrations: %s", self.name, e)
            return []
        except ValueError as e:
            logger.warning("%s: failed to parse Home Assistant integrations JSON: %s", self.name, e)
            return []

        return _extract_integration_records(data)


def _extract_integration_records(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        logger.warning("home_assistant_integrations: malformed payload: expected list or object")
        return []

    for key in ("integrations", "components", "items", "data"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    if all(isinstance(value, dict) for value in data.values()):
        records: list[dict] = []
        for key, value in data.items():
            record = dict(value)
            record.setdefault("domain", key)
            records.append(record)
        return records

    logger.warning("home_assistant_integrations: malformed payload: missing integrations list")
    return []


def _integration_to_signal(
    item: dict,
    *,
    adapter_name: str,
    source_url: str,
    published_at: datetime | None,
) -> Signal:
    domain = _integration_domain(item)
    if domain is None:
        raise ValueError("missing domain")

    title = _string_or_none(item.get("name")) or _title_from_domain(domain)
    description = _description(item, title=title, domain=domain)
    integration_url = _integration_url(item, domain)
    quality_scale = _string_or_none(item.get("quality_scale"))
    iot_class = _string_or_none(item.get("iot_class"))
    integration_type = _string_or_none(item.get("integration_type"))
    categories = _string_list(item.get("categories") or item.get("category"))

    metadata = {
        "signal_role": "market",
        "domain": domain,
        "name": title,
        "description": _string_or_none(item.get("description")),
        "categories": categories,
        "quality_scale": quality_scale,
        "iot_class": iot_class,
        "integration_type": integration_type,
        "integration_url": integration_url,
        "documentation_url": _string_or_none(item.get("documentation")),
        "source_url": source_url,
    }

    return Signal(
        id=f"{adapter_name}:{domain.lower()}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{title} Home Assistant integration",
        content=description[:500],
        url=integration_url,
        published_at=published_at,
        tags=_build_tags(domain, categories, quality_scale, iot_class, integration_type),
        credibility=_credibility(quality_scale, iot_class, integration_type),
        metadata=metadata,
    )


def _description(item: dict, *, title: str, domain: str) -> str:
    description = _string_or_none(item.get("description"))
    if description:
        return description

    parts = [f"{title} ({domain}) is a Home Assistant integration"]
    integration_type = _string_or_none(item.get("integration_type"))
    iot_class = _string_or_none(item.get("iot_class"))
    quality_scale = _string_or_none(item.get("quality_scale"))
    if integration_type:
        parts.append(f"with integration type {integration_type}")
    if iot_class:
        parts.append(f"and IoT class {iot_class}")
    if quality_scale:
        parts.append(f"rated {quality_scale} on the integration quality scale")
    return " ".join(parts) + "."


def _matches_filters(item: dict, *, integrations: list[str], categories: list[str]) -> bool:
    if not integrations and not categories:
        return True

    values = _filter_values(item)
    integration_match = not integrations or any(
        _term_matches(term, values) for term in integrations
    )
    category_match = not categories or any(_term_matches(term, values) for term in categories)
    return integration_match and category_match


def _filter_values(item: dict) -> list[str]:
    values = [
        _integration_domain(item),
        _string_or_none(item.get("name")),
        _string_or_none(item.get("description")),
        _string_or_none(item.get("quality_scale")),
        _string_or_none(item.get("iot_class")),
        _string_or_none(item.get("integration_type")),
        *_string_list(item.get("categories") or item.get("category")),
        *_string_list(item.get("brands")),
        *_string_list(item.get("ha_category")),
    ]
    return [value.lower() for value in values if isinstance(value, str) and value]


def _term_matches(term: str, values: list[str]) -> bool:
    normalized = term.strip().lower()
    return bool(normalized) and any(normalized in value for value in values)


def _integration_domain(item: dict) -> str | None:
    return _string_or_none(item.get("domain") or item.get("slug") or item.get("id"))


def _integration_url(item: dict, domain: str) -> str:
    return (
        _string_or_none(item.get("url"))
        or _string_or_none(item.get("integration_url"))
        or _string_or_none(item.get("documentation"))
        or HOME_ASSISTANT_INTEGRATION_WEB_URL.format(domain=quote(domain, safe=""))
    )


def _integration_datetime(item: dict) -> datetime | None:
    for key in ("updated_at", "last_updated", "released_at", "created_at"):
        parsed = _parse_datetime(item.get(key))
        if parsed is not None:
            return parsed
    return None


def _build_tags(
    domain: str,
    categories: list[str],
    quality_scale: str | None,
    iot_class: str | None,
    integration_type: str | None,
) -> list[str]:
    tags = ["home-assistant", domain]
    tags.extend(categories)
    if quality_scale:
        tags.append(f"quality:{quality_scale}")
    if iot_class:
        tags.append(f"iot:{iot_class}")
    if integration_type:
        tags.append(f"type:{integration_type}")
    return _dedupe(tags)[:10]


def _credibility(
    quality_scale: str | None,
    iot_class: str | None,
    integration_type: str | None,
) -> float:
    quality_scores = {
        "platinum": 0.45,
        "gold": 0.38,
        "silver": 0.31,
        "bronze": 0.24,
        "internal": 0.3,
        "legacy": 0.08,
        "no_score": 0.05,
    }
    score = 0.35 + quality_scores.get((quality_scale or "").lower().replace(" ", "_"), 0.1)
    if iot_class and iot_class.startswith("local_"):
        score += 0.08
    if integration_type in {"hub", "device", "service"}:
        score += 0.04
    return min(round(score, 3), 1.0)


def _cutoff(max_age_days: int | None) -> datetime | None:
    if max_age_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_terms(value: object, *, default: Iterable[str]) -> list[str]:
    if value is None:
        values = list(default)
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, dict):
        values = list(value)
    else:
        values = []

    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        term = value.strip().strip("/")
        key = term.lower()
        if not term or key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Iterable) or isinstance(value, dict):
        return []

    values: list[str] = []
    for item in value:
        string_value = _string_or_none(item)
        if string_value:
            values.append(string_value)
    return values


def _positive_int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _title_from_domain(domain: str) -> str:
    return domain.replace("_", " ").replace("-", " ").title()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
