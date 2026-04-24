"""Maven Central source adapter - Java/JVM ecosystem package activity."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

MAVEN_CENTRAL_SEARCH = "https://search.maven.org/solrsearch/select"
MAVEN_CENTRAL_ARTIFACT_PAGE = "https://central.sonatype.com/artifact/{group_id}/{artifact_id}"
MAVEN_CENTRAL_REPOSITORY = "https://repo1.maven.org/maven2/{group_path}/{artifact_id}/{version}/"

_DEFAULT_QUERIES = ["ai", "llm", "agent", "mcp", "openai"]
_DEFAULT_COORDINATES = [
    "dev.langchain4j:langchain4j",
    "dev.langchain4j:langchain4j-open-ai",
    "org.springframework.ai:spring-ai-core",
    "com.theokanning.openai-gpt3-java:service",
    "io.modelcontextprotocol.sdk:mcp",
]


class MavenCentralAdapter(SourceAdapter):
    """Fetch Maven Central package metadata for configured coordinates and search terms."""

    @property
    def name(self) -> str:
        return "maven_central"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def coordinates(self) -> list[str]:
        return self._configured_terms("coordinates", _DEFAULT_COORDINATES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[tuple[str, str]] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for coordinate in self.coordinates:
                if len(signals) >= limit:
                    break

                parsed = _parse_coordinate(coordinate)
                if parsed is None:
                    logger.warning("%s: skipping malformed Maven coordinate: %s", self.name, coordinate)
                    continue

                group_id, artifact_id = parsed
                data = await self._fetch_json(
                    client,
                    context=f"coordinate '{coordinate}'",
                    params={
                        "q": f'g:"{group_id}" AND a:"{artifact_id}"',
                        "rows": 1,
                        "wt": "json",
                    },
                )
                if data is None:
                    continue

                self._append_package_signals(
                    signals,
                    _docs_from_response(data),
                    limit=limit,
                    seen_packages=seen_packages,
                    coordinate=coordinate,
                )

            for query in self.queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    context=f"query '{query}'",
                    params={
                        "q": query,
                        "rows": min(10, limit - len(signals)),
                        "wt": "json",
                    },
                )
                if data is None:
                    continue

                self._append_package_signals(
                    signals,
                    _docs_from_response(data),
                    limit=limit,
                    seen_packages=seen_packages,
                    search_query=query,
                )

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                MAVEN_CENTRAL_SEARCH,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-maven-central-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Maven Central data for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    def _append_package_signals(
        self,
        signals: list[Signal],
        docs: list[dict],
        *,
        limit: int,
        seen_packages: set[tuple[str, str]],
        coordinate: str | None = None,
        search_query: str | None = None,
    ) -> None:
        for doc in docs:
            if len(signals) >= limit:
                break

            try:
                group_id = _string_or_none(doc.get("g"))
                artifact_id = _string_or_none(doc.get("a"))
                if group_id is None or artifact_id is None:
                    continue

                package_key = (group_id.lower(), artifact_id.lower())
                if package_key in seen_packages:
                    continue

                signal = _doc_to_signal(
                    doc,
                    adapter_name=self.name,
                    coordinate=coordinate,
                    search_query=search_query,
                )
                if signal is None:
                    continue

                seen_packages.add(package_key)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Maven Central document: %s", self.name, e)


def _doc_to_signal(
    doc: dict,
    *,
    adapter_name: str,
    coordinate: str | None = None,
    search_query: str | None = None,
) -> Signal | None:
    group_id = _string_or_none(doc.get("g"))
    artifact_id = _string_or_none(doc.get("a"))
    if group_id is None or artifact_id is None:
        return None

    latest_version = _string_or_none(doc.get("latestVersion")) or _string_or_none(doc.get("v")) or ""
    version_count = _int_or_none(doc.get("versionCount")) or 0
    published_at = _parse_timestamp(doc.get("timestamp"))
    source_url = MAVEN_CENTRAL_ARTIFACT_PAGE.format(group_id=group_id, artifact_id=artifact_id)
    repository_url = _repository_url(group_id, artifact_id, latest_version)
    tags = _build_tags(doc, search_query=search_query)
    package_id = f"{group_id}:{artifact_id}"

    metadata = {
        "package_ecosystem": "maven",
        "package_id": package_id,
        "group_id": group_id,
        "artifact_id": artifact_id,
        "latest_version": latest_version,
        "version": latest_version,
        "version_count": version_count,
        "repository_id": _string_or_none(doc.get("repositoryId")),
        "repository_url": repository_url,
        "source_url": source_url,
        "search_query": search_query,
        "coordinate": coordinate,
        "packaging": _string_or_none(doc.get("p")),
        "timestamp": doc.get("timestamp"),
        "tags": tags,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_id}@{latest_version}" if latest_version else package_id,
        content=_content(doc, package_id),
        url=source_url,
        author=group_id,
        published_at=published_at,
        tags=tags,
        credibility=_credibility(version_count=version_count, published_at=published_at),
        metadata=metadata,
    )


def _docs_from_response(data: dict) -> list[dict]:
    response = data.get("response")
    if not isinstance(response, dict):
        return []

    docs = response.get("docs")
    if not isinstance(docs, list):
        return []

    return [doc for doc in docs if isinstance(doc, dict)]


def _parse_coordinate(value: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _repository_url(group_id: str, artifact_id: str, version: str) -> str | None:
    if not version:
        return None
    return MAVEN_CENTRAL_REPOSITORY.format(
        group_path=group_id.replace(".", "/"),
        artifact_id=artifact_id,
        version=version,
    )


def _content(doc: dict, package_id: str) -> str:
    text_values = [value for value in doc.get("text") or [] if isinstance(value, str)]
    if text_values:
        return " ".join(text_values)[:500]
    return package_id


def _build_tags(doc: dict, *, search_query: str | None = None) -> list[str]:
    raw_tags: list[str] = []
    for value in [doc.get("p"), *(doc.get("tags") or [])]:
        if isinstance(value, str):
            raw_tags.append(value.strip())

    if search_query:
        raw_tags.append(search_query)

    seen: set[str] = set()
    tags: list[str] = []
    for tag in raw_tags:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags[:10]


def _credibility(*, version_count: int, published_at: datetime | None) -> float:
    version_score = min(math.log10(version_count + 1) / 3, 0.55)
    freshness_score = 0.0

    if published_at is not None:
        age_days = (datetime.now(timezone.utc) - published_at).days
        if age_days <= 30:
            freshness_score = 0.25
        elif age_days <= 180:
            freshness_score = 0.2
        elif age_days <= 365:
            freshness_score = 0.12
        elif age_days <= 730:
            freshness_score = 0.06

    return min(round(0.1 + version_score + freshness_score, 3), 1.0)


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)


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
