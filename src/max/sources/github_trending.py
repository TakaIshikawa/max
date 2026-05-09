"""GitHub Trending source adapter — repository momentum from trending pages."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urljoin

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com"
_DEFAULT_TOPICS = ["ai", "llm", "mcp", "developer-tools", "python", "typescript"]
_VALID_SINCE_PERIODS = {"daily", "weekly", "monthly"}


@dataclass
class TrendingRepository:
    owner: str
    name: str
    description: str = ""
    stars: int | None = None
    forks: int | None = None
    language: str | None = None
    stars_today: int | None = None
    url: str = ""
    trending_language: str | None = None


@dataclass
class _Article:
    links: list[tuple[str, str]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    spans: list[tuple[dict[str, str], str]] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)


class _TrendingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.articles: list[_Article] = []
        self._article: _Article | None = None
        self._article_depth = 0
        self._link_href: str | None = None
        self._link_parts: list[str] = []
        self._paragraph_parts: list[str] | None = None
        self._span_attrs: dict[str, str] | None = None
        self._span_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "article" and _has_class(attr_map, "Box-row"):
            self._article = _Article()
            self._article_depth = 1
            return

        if self._article is None:
            return

        self._article_depth += 1
        if tag == "a":
            self._link_href = attr_map.get("href", "")
            self._link_parts = []
        elif tag == "p":
            self._paragraph_parts = []
        elif tag == "span":
            self._span_attrs = attr_map
            self._span_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._article is None:
            return

        if tag == "a" and self._link_href is not None:
            self._article.links.append((self._link_href, _clean_text(" ".join(self._link_parts))))
            self._link_href = None
            self._link_parts = []
        elif tag == "p" and self._paragraph_parts is not None:
            paragraph = _clean_text(" ".join(self._paragraph_parts))
            if paragraph:
                self._article.paragraphs.append(paragraph)
            self._paragraph_parts = None
        elif tag == "span" and self._span_attrs is not None:
            self._article.spans.append((self._span_attrs, _clean_text(" ".join(self._span_parts))))
            self._span_attrs = None
            self._span_parts = []

        self._article_depth -= 1
        if tag == "article" and self._article_depth <= 0:
            self.articles.append(self._article)
            self._article = None
            self._article_depth = 0

    def handle_data(self, data: str) -> None:
        if self._article is None:
            return
        self._article.text_parts.append(data)
        if self._link_href is not None:
            self._link_parts.append(data)
        if self._paragraph_parts is not None:
            self._paragraph_parts.append(data)
        if self._span_attrs is not None:
            self._span_parts.append(data)


class GitHubTrendingAdapter(SourceAdapter):
    """Fetch GitHub Trending repository pages as market demand signals."""

    @property
    def name(self) -> str:
        return "github_trending"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def languages(self) -> list[str]:
        configured = self._config.get("languages")
        if configured is None:
            return [""]
        if isinstance(configured, str):
            configured = [configured]
        languages: list[str] = []
        seen: set[str] = set()
        for value in configured:
            if not isinstance(value, str):
                continue
            language = value.strip()
            key = language.lower()
            if key in seen:
                continue
            seen.add(key)
            languages.append(language)
        return languages or [""]

    @property
    def since(self) -> str:
        since = str(self._config.get("since", "daily")).strip().lower()
        return since if since in _VALID_SINCE_PERIODS else "daily"

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url", GITHUB_TRENDING_URL)).rstrip("/")

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen_repositories: set[str] = set()
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "max-signal-fetcher/1.0",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for language in self.languages:
                if len(signals) >= limit:
                    break
                try:
                    response = await fetch_with_retry(
                        _trending_url(self.base_url, language, self.since),
                        client,
                        adapter_name=self.name,
                    )
                    repositories = _parse_trending_html(
                        response.text,
                        base_url=self.base_url,
                        trending_language=language or None,
                    )
                except Exception:
                    logger.warning(
                        "GitHub Trending fetch failed for language: %s",
                        language or "all",
                        exc_info=True,
                    )
                    continue

                for repo in repositories:
                    key = f"{repo.owner}/{repo.name}".lower()
                    if key in seen_repositories:
                        continue
                    seen_repositories.add(key)
                    signals.append(_repository_to_signal(repo, self.name, self.since, self.topics))
                    if len(signals) >= limit:
                        break

        return signals[:limit]


def _trending_url(base_url: str, language: str, since: str) -> str:
    path = "/trending"
    if language:
        path = f"{path}/{quote(language, safe='')}"
    base_with_slash = f"{base_url.rstrip('/')}/"
    clean_path = path.lstrip('/')
    return f"{urljoin(base_with_slash, clean_path)}?{urlencode({'since': since})}"


def _parse_trending_html(
    html: str,
    *,
    base_url: str,
    trending_language: str | None = None,
) -> list[TrendingRepository]:
    parser = _TrendingParser()
    try:
        parser.feed(html or "")
    except Exception:
        logger.debug("GitHub Trending HTML parser failed", exc_info=True)
        return []

    repositories: list[TrendingRepository] = []
    for article in parser.articles:
        repository = _article_to_repository(
            article,
            base_url=base_url,
            trending_language=trending_language,
        )
        if repository is not None:
            repositories.append(repository)
    return repositories


def _article_to_repository(
    article: _Article,
    *,
    base_url: str,
    trending_language: str | None,
) -> TrendingRepository | None:
    repo_link = _repository_link(article.links)
    if repo_link is None:
        return None

    href, text = repo_link
    owner, name = _parse_repository_name(text, href)
    if not owner or not name:
        return None

    return TrendingRepository(
        owner=owner,
        name=name,
        description=article.paragraphs[0] if article.paragraphs else "",
        stars=_link_count(article.links, "stargazers"),
        forks=_link_count(article.links, "forks")
        or _link_count(article.links, "network/members"),
        language=_programming_language(article.spans),
        stars_today=_stars_today(" ".join(article.text_parts)),
        url=urljoin(f"{base_url.rstrip('/')}/", f"{owner}/{name}"),
        trending_language=trending_language,
    )


def _repository_to_signal(
    repo: TrendingRepository,
    adapter_name: str,
    since: str,
    topics: list[str],
) -> Signal:
    full_name = f"{repo.owner}/{repo.name}"
    stars = repo.stars or 0
    content = repo.description or f"{full_name} is trending on GitHub."
    tags = _build_tags(repo.language, repo.trending_language, topics)
    return Signal(
        source_type=SignalSourceType.TRENDING,
        source_adapter=adapter_name,
        title=full_name,
        content=content[:500],
        url=repo.url,
        author=repo.owner,
        tags=tags,
        credibility=min(stars / 50_000, 1.0),
        metadata={
            "repository": full_name,
            "owner": repo.owner,
            "name": repo.name,
            "description": repo.description,
            "stars": repo.stars,
            "forks": repo.forks,
            "language": repo.language,
            "stars_today": repo.stars_today,
            "trending_language": repo.trending_language,
            "since": since,
            "topics": topics[:10],
            "signal_role": "market",
        },
    )


def _repository_link(links: list[tuple[str, str]]) -> tuple[str, str] | None:
    for href, text in links:
        if _repo_path(href) is not None and not _is_repository_subpage(href):
            return href, text
    return None


def _parse_repository_name(text: str, href: str) -> tuple[str, str]:
    path_match = _repo_path(href)
    if path_match is not None:
        return path_match

    parts = [part.strip() for part in text.split("/") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


def _repo_path(href: str) -> tuple[str, str] | None:
    match = re.match(r"^/([^/\s]+)/([^/\s?#]+)(?:[?#].*)?$", href.strip())
    if not match:
        return None
    owner, name = match.groups()
    return unescape(owner), unescape(name)


def _is_repository_subpage(href: str) -> bool:
    return bool(re.match(r"^/[^/\s]+/[^/\s]+/", href.strip()))


def _link_count(links: list[tuple[str, str]], path_fragment: str) -> int | None:
    for href, text in links:
        if path_fragment in href:
            return _parse_count(text)
    return None


def _programming_language(spans: list[tuple[dict[str, str], str]]) -> str | None:
    for attrs, text in spans:
        if attrs.get("itemprop") == "programmingLanguage" and text:
            return text
    return None


def _stars_today(text: str) -> int | None:
    match = re.search(r"([\d,.]+[kKmM]?)\s+stars?\s+today", _clean_text(text))
    return _parse_count(match.group(1)) if match else None


def _parse_count(value: str) -> int | None:
    cleaned = _clean_text(value).replace(",", "")
    match = re.search(r"([\d.]+)\s*([kKmM]?)", cleaned)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def _build_tags(
    language: str | None,
    trending_language: str | None,
    topics: list[str],
) -> list[str]:
    tags = {"github", "trending", "repository"}
    for value in [language, trending_language, *topics]:
        if not value:
            continue
        tag = value.strip().lower().replace(" ", "-")
        if tag:
            tags.add(tag)
    return sorted(tags)[:12]


def _has_class(attrs: dict[str, str], class_name: str) -> bool:
    return class_name in attrs.get("class", "").split()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()
