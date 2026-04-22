"""GitHub awesome-list source adapter for curated markdown links."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_GITHUB_HOSTS = {"github.com", "www.github.com"}


@dataclass(frozen=True)
class AwesomeListItem:
    """Parsed awesome-list markdown item."""

    title: str
    url: str
    description: str
    section_heading: str
    raw_line: str
    document_heading: str = ""


class AwesomeListsAdapter(SourceAdapter):
    """Fetch curated GitHub awesome-list markdown links as registry signals."""

    @property
    def name(self) -> str:
        return "awesome_lists"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def lists(self) -> list[str]:
        configured = self._config.get("lists", [])
        if not isinstance(configured, list):
            return []

        urls: list[str] = []
        for item in configured:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
            elif isinstance(item, dict):
                url = item.get("url") or item.get("list_url")
                if isinstance(url, str) and url.strip():
                    urls.append(url.strip())
        return urls

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", [])

    @property
    def include_descriptions(self) -> bool:
        value = self._config.get("include_descriptions", True)
        return bool(value)

    @property
    def github_token(self) -> str | None:
        token = self._config.get("github_token") or self._config.get("token")
        return token.strip() if isinstance(token, str) and token.strip() else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()

        headers = {
            "User-Agent": "max-awesome-lists-adapter/0.1",
            "Accept": "text/plain, text/markdown, */*",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            for list_url in self.lists:
                if len(signals) >= limit:
                    break

                raw_url = github_url_to_raw(list_url)
                try:
                    response = await fetch_with_retry(
                        raw_url,
                        client,
                        adapter_name=self.name,
                    )
                except Exception:
                    logger.warning("Awesome list fetch failed: %s", list_url, exc_info=True)
                    continue

                for item in parse_awesome_markdown(response.text):
                    if len(signals) >= limit:
                        break
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)
                    if not _matches_topics(item, self.topics):
                        continue

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.REGISTRY,
                            source_adapter=self.name,
                            title=item.title,
                            content=item.description if self.include_descriptions else "",
                            url=item.url,
                            tags=_dedupe(self.topics + _list_tags(list_url)),
                            credibility=0.65,
                            metadata={
                                "list_url": list_url,
                                "raw_list_url": raw_url,
                                "section_heading": item.section_heading,
                                "repository_owner": _github_repo(list_url)[0],
                                "repository_name": _github_repo(list_url)[1],
                                "raw_line": item.raw_line,
                            },
                        )
                    )

        return signals[:limit]


def github_url_to_raw(url: str) -> str:
    """Convert common GitHub blob URLs to raw markdown URLs."""
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() not in _GITHUB_HOSTS:
        return url.strip()

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, _, branch = parts[:4]
        path = "/".join(parts[4:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

    return url.strip()


def parse_awesome_markdown(markdown: str) -> list[AwesomeListItem]:
    """Parse markdown list items containing links and optional descriptions."""
    items: list[AwesomeListItem] = []
    document_heading = ""
    section_heading = ""

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            heading = _clean_text(heading_match.group(2))
            if len(heading_match.group(1)) == 1:
                document_heading = heading
            section_heading = heading
            continue

        if not _LIST_MARKER_RE.match(raw_line):
            continue

        link_match = _MARKDOWN_LINK_RE.search(raw_line)
        if link_match is None:
            continue

        title = _clean_text(link_match.group(1))
        url = link_match.group(2).strip()
        if not title or not _is_http_url(url):
            continue

        description = _extract_description(raw_line, link_match.end())
        items.append(
            AwesomeListItem(
                title=title,
                url=url,
                description=description,
                section_heading=section_heading,
                raw_line=raw_line.strip(),
                document_heading=document_heading,
            )
        )

    return items


def _extract_description(raw_line: str, link_end: int) -> str:
    description = raw_line[link_end:].strip()
    description = re.sub(r"^\s*(?:[-:–—]\s*)", "", description)
    description = re.sub(r"\s+", " ", description)
    return _clean_text(description)


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", value).strip()


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _matches_topics(item: AwesomeListItem, topics: list[str]) -> bool:
    if not topics:
        return True
    haystack = " ".join(
        [item.title, item.description, item.section_heading, item.document_heading, item.url]
    ).casefold()
    return any(topic.casefold() in haystack for topic in topics)


def _github_repo(url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() not in _GITHUB_HOSTS | {"raw.githubusercontent.com"}:
        return None, None

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def _list_tags(list_url: str) -> list[str]:
    owner, repo = _github_repo(list_url)
    if owner and repo:
        return [owner, repo]

    parsed = urlparse(list_url)
    if parsed.netloc:
        path_name = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return [tag for tag in [parsed.netloc, path_name] if tag]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        clean = value.strip() if isinstance(value, str) else ""
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped
