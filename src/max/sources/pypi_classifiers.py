"""PyPI classifier trend source adapter -- ecosystem category momentum signals."""

from __future__ import annotations

import logging
import math
import re
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PYPI_JSON_BASE_URL = "https://pypi.org/pypi"
PYPI_PROJECT_BASE_URL = "https://pypi.org/project"


class PyPIClassifiersAdapter(SourceAdapter):
    """Aggregate PyPI package classifiers into category momentum signals."""

    @property
    def name(self) -> str:
        return "pypi_classifiers"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def max_items(self) -> int:
        return max(int(self._config.get("max_items", 30)), 1)

    @property
    def representatives_per_classifier(self) -> int:
        return max(int(self._config.get("representatives_per_classifier", 3)), 1)

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url", PYPI_JSON_BASE_URL)).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(min(limit, self.max_items), 0)
        if item_limit == 0:
            return []

        packages = _normalize_package_names(self.packages)
        if not packages:
            return []

        records: list[dict] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for package in packages:
                payload = await self._fetch_package_json(client, package)
                if payload is None:
                    continue

                record = _package_record(payload, fallback_package=package)
                if record is not None:
                    records.append(record)

        trends = _classifier_trends(
            records,
            representatives_per_classifier=self.representatives_per_classifier,
        )
        return [
            _classifier_trend_to_signal(trend, adapter_name=self.name)
            for trend in trends[:item_limit]
        ]

    async def _fetch_package_json(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _package_json_url(self.base_url, package)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-pypi-classifiers-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch package metadata for %s: %s", self.name, package, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, package, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse package metadata for %s: %s", self.name, package, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed package metadata for %s", self.name, package)
            return None
        return payload


def _package_record(payload: dict, *, fallback_package: str) -> dict | None:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    classifiers = _string_list(info.get("classifiers"))
    if not classifiers:
        return None

    package_name = str(info.get("name") or fallback_package).strip() or fallback_package
    normalized_package = _normalize_package_name(package_name) or fallback_package
    package_url = str(info.get("package_url") or _package_project_url(normalized_package))
    project_urls = info.get("project_urls") if isinstance(info.get("project_urls"), dict) else {}
    growth = _classifier_growth(payload, info)

    return {
        "package_name": package_name,
        "normalized_package_name": normalized_package,
        "package_url": package_url,
        "project_urls": {
            str(key): str(value)
            for key, value in project_urls.items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        },
        "classifiers": classifiers,
        "growth": growth,
    }


def _classifier_trends(
    records: list[dict],
    *,
    representatives_per_classifier: int,
) -> list[dict]:
    buckets: dict[str, dict] = {}

    for record in records:
        for classifier in record["classifiers"]:
            bucket = buckets.setdefault(
                classifier,
                {
                    "classifier": classifier,
                    "count": 0,
                    "growth": 0.0,
                    "packages": [],
                    "source_urls": [],
                },
            )
            bucket["count"] += 1
            bucket["growth"] += float(record["growth"].get(classifier, 0.0))

            package_name = record["package_name"]
            if package_name not in bucket["packages"]:
                bucket["packages"].append(package_name)

            for url in _source_urls(record):
                if url not in bucket["source_urls"]:
                    bucket["source_urls"].append(url)

    trends = list(buckets.values())
    for trend in trends:
        trend["representative_packages"] = trend["packages"][:representatives_per_classifier]
        trend["source_urls"] = trend["source_urls"][:representatives_per_classifier]
        trend["growth"] = _stable_number(trend["growth"])

    trends.sort(
        key=lambda trend: (
            -float(trend["growth"]),
            -int(trend["count"]),
            str(trend["classifier"]).lower(),
        )
    )
    return trends


def _classifier_trend_to_signal(trend: dict, *, adapter_name: str) -> Signal:
    classifier = trend["classifier"]
    count = int(trend["count"])
    growth = float(trend["growth"])
    representative_packages = list(trend["representative_packages"])
    source_urls = list(trend["source_urls"])

    content = f"{classifier} appears on {count} sampled PyPI package"
    if count != 1:
        content += "s"
    if representative_packages:
        content += f": {', '.join(representative_packages)}."
    else:
        content += "."
    if growth:
        content += f" Growth metadata score: {_stable_number(growth)}."

    return Signal(
        source_type=SignalSourceType.TRENDING,
        source_adapter=adapter_name,
        title=f"PyPI classifier trend: {classifier}",
        content=content,
        url=source_urls[0] if source_urls else "https://pypi.org/",
        tags=_build_tags(classifier),
        credibility=_credibility(count=count, growth=growth),
        metadata={
            "signal_role": "market",
            "classifier_name": classifier,
            "classifier": classifier,
            "count": count,
            "growth": _stable_number(growth),
            "representative_packages": representative_packages,
            "package_names": representative_packages,
            "source_urls": source_urls,
        },
    )


def _classifier_growth(payload: dict, info: dict) -> dict[str, float]:
    for container in (payload, info):
        for key in ("classifier_growth", "classifier_trends", "classifier_momentum"):
            value = container.get(key)
            if isinstance(value, dict):
                return {
                    str(classifier): float(score)
                    for classifier, score in value.items()
                    if isinstance(classifier, str) and _is_number(score)
                }
    return {}


def _source_urls(record: dict) -> list[str]:
    urls = [record["package_url"]]
    urls.extend(record["project_urls"].values())

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not isinstance(url, str):
            continue
        cleaned = url.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _build_tags(classifier: str) -> list[str]:
    tags = ["python", "pypi", "classifier", "trend"]
    parts = re.split(r"[^a-z0-9]+", classifier.lower())
    tags.extend(part for part in parts if part and part not in {"and", "or"})

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(*, count: int, growth: float) -> float:
    count_score = min(math.log10(count + 1) / 2, 0.4)
    growth_score = min(max(growth, 0.0) / 10, 0.3)
    return min(round(0.3 + count_score + growth_score, 3), 1.0)


def _normalize_package_names(values: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_package_name(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return names


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        strings.append(text)
    return strings


def _package_json_url(base_url: str, package: str) -> str:
    return f"{base_url}/{quote(package)}/json"


def _package_project_url(package: str) -> str:
    return f"{PYPI_PROJECT_BASE_URL}/{quote(package)}/"


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _stable_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 3)
