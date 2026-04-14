"""Prior art detection — search public sources for existing implementations."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field

import httpx

from max.embeddings.engine import _cosine_similarity, embed_text
from max.types.buildable_unit import BuildableUnit

logger = logging.getLogger(__name__)

# ── Stop words for query construction ────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall", "that",
    "this", "these", "those", "it", "its", "not", "no", "nor", "so",
    "if", "then", "than", "too", "very", "just", "about", "above",
    "after", "before", "between", "into", "through", "during", "each",
    "all", "both", "more", "most", "other", "some", "such", "only",
    "own", "same", "also", "how", "what", "which", "who", "whom",
    "when", "where", "why", "up", "out", "off", "over", "under",
    "again", "further", "once", "here", "there", "any", "every",
    "based", "using", "via", "across", "enables", "provides",
})

# ── Rate limit configuration ─────────────────────────────────────

_RATE_LIMITS: dict[str, tuple[int, float]] = {
    # (max_concurrent, delay_seconds)
    "github": (2, 2.0),
    "npm": (5, 0.5),
    "pypi": (3, 1.0),
    "product_hunt": (1, 3.0),
}


# ── Data structures ──────────────────────────────────────────────

@dataclass
class PriorArtMatch:
    source: str  # github | npm | pypi | product_hunt
    title: str
    url: str
    description: str
    relevance_score: float = 0.0
    match_signals: dict = field(default_factory=dict)
    search_query: str = ""


@dataclass
class PriorArtResult:
    buildable_unit_id: str
    matches: list[PriorArtMatch]
    status: str  # clear | weak_match | strong_match


# ── Query construction ───────────────────────────────────────────

def _extract_keywords(text: str, max_tokens: int = 6) -> list[str]:
    """Extract top keywords from text, removing stop words."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
    filtered = [w for w in words if w not in _STOP_WORDS and len(w) > 2]
    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for w in filtered:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_tokens]


def build_search_queries(unit: BuildableUnit) -> list[str]:
    """Generate search queries for a buildable unit."""
    queries: list[str] = []
    # Query 1: title directly
    queries.append(unit.title)
    # Query 2: keywords from title + one_liner
    keywords = _extract_keywords(f"{unit.title} {unit.one_liner}")
    if keywords:
        queries.append(" ".join(keywords))
    return queries


# ── Source selection ──────────────────────────────────────────────

_JS_INDICATORS = {"javascript", "typescript", "node", "js", "ts", "react", "vue", "next"}
_PY_INDICATORS = {"python", "py", "django", "flask", "fastapi"}


def select_sources(unit: BuildableUnit) -> list[str]:
    """Select which sources to search based on category and stack."""
    sources: list[str] = ["github"]  # Always search GitHub

    category = unit.category.lower()
    stack_str = str(unit.suggested_stack).lower()

    # npm: library, mcp_server, cli_tool, or JS/TS in stack
    if category in ("library", "mcp_server", "cli_tool") or _JS_INDICATORS & set(
        re.findall(r"\w+", stack_str)
    ):
        sources.append("npm")

    # PyPI: library, cli_tool, or Python in stack
    if category in ("library", "cli_tool") or _PY_INDICATORS & set(
        re.findall(r"\w+", stack_str)
    ):
        sources.append("pypi")

    # Product Hunt: application, feature
    if category in ("application", "feature"):
        sources.append("product_hunt")

    return sources


# ── API key resolution ───────────────────────────────────────────

def _resolve_github_token() -> str | None:
    """Resolve GitHub token: env var first, then vault."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "github/token"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _resolve_product_hunt_token() -> str | None:
    """Resolve Product Hunt token: env var first, then vault."""
    token = os.environ.get("PRODUCT_HUNT_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "product_hunt/token"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ── Search functions ─────────────────────────────────────────────

async def _search_github(
    query: str, client: httpx.AsyncClient, *, extra_headers: dict[str, str] | None = None,
) -> list[PriorArtMatch]:
    """Search GitHub repositories."""
    matches: list[PriorArtMatch] = []
    try:
        resp = await client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 5},
            headers=extra_headers or {},
        )
        if resp.status_code != 200:
            logger.warning("GitHub search returned %d for query: %s", resp.status_code, query)
            return matches
        data = resp.json()
        for repo in data.get("items", [])[:5]:
            matches.append(PriorArtMatch(
                source="github",
                title=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                description=repo.get("description", "") or "",
                match_signals={
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language", ""),
                    "updated_at": repo.get("updated_at", ""),
                },
                search_query=query,
            ))
    except Exception:
        logger.warning("GitHub search failed for query: %s", query, exc_info=True)
    return matches


async def _search_npm(query: str, client: httpx.AsyncClient, **_: object) -> list[PriorArtMatch]:
    """Search npm registry."""
    matches: list[PriorArtMatch] = []
    try:
        resp = await client.get(
            "https://registry.npmjs.org/-/v1/search",
            params={"text": query, "size": 5},
        )
        if resp.status_code != 200:
            logger.warning("npm search returned %d for query: %s", resp.status_code, query)
            return matches
        data = resp.json()
        for obj in data.get("objects", [])[:5]:
            pkg = obj.get("package", {})
            matches.append(PriorArtMatch(
                source="npm",
                title=pkg.get("name", ""),
                url=pkg.get("links", {}).get("npm", f"https://www.npmjs.com/package/{pkg.get('name', '')}"),
                description=pkg.get("description", "") or "",
                match_signals={
                    "version": pkg.get("version", ""),
                    "score_detail": {
                        k: round(v, 3) for k, v in obj.get("score", {}).get("detail", {}).items()
                    },
                },
                search_query=query,
            ))
    except Exception:
        logger.warning("npm search failed for query: %s", query, exc_info=True)
    return matches


async def _search_pypi(query: str, client: httpx.AsyncClient, **_: object) -> list[PriorArtMatch]:
    """Search PyPI packages."""
    matches: list[PriorArtMatch] = []
    try:
        resp = await client.get(
            "https://pypi.org/search/",
            params={"q": query},
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
        # PyPI search doesn't have a proper JSON API; use the XMLRPC or simple search
        # Fall back to a simpler approach: search via pypi.org/pypi/{name}/json
        # Use the warehouse simple API search endpoint
        resp = await client.get(
            "https://pypi.org/simple/",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        )
        if resp.status_code != 200:
            logger.warning("PyPI index returned %d", resp.status_code)
            return matches

        # PyPI doesn't have a great search API. Use Google site search as fallback.
        resp = await client.get(
            "https://pypi.org/search/",
            params={"q": query, "page": "1"},
        )
        if resp.status_code != 200:
            return matches

        # Parse HTML results (minimal extraction)
        html = resp.text
        # Extract package names from search result snippets
        pattern = r'<a class="package-snippet" href="/project/([^/"]+)/">'
        pkg_names = re.findall(pattern, html)[:5]

        for name in pkg_names:
            # Fetch package metadata
            try:
                meta_resp = await client.get(f"https://pypi.org/pypi/{name}/json")
                if meta_resp.status_code != 200:
                    continue
                meta = meta_resp.json()
                info = meta.get("info", {})
                matches.append(PriorArtMatch(
                    source="pypi",
                    title=info.get("name", name),
                    url=info.get("package_url", f"https://pypi.org/project/{name}/"),
                    description=info.get("summary", "") or "",
                    match_signals={
                        "version": info.get("version", ""),
                        "author": info.get("author", ""),
                        "requires_python": info.get("requires_python", ""),
                    },
                    search_query=query,
                ))
            except Exception:
                continue
    except Exception:
        logger.warning("PyPI search failed for query: %s", query, exc_info=True)
    return matches


async def _search_product_hunt(query: str, client: httpx.AsyncClient, **_: object) -> list[PriorArtMatch]:
    """Search Product Hunt posts via GraphQL API."""
    matches: list[PriorArtMatch] = []
    token = _resolve_product_hunt_token()
    if not token:
        logger.debug("No Product Hunt token — skipping")
        return matches

    try:
        graphql_query = """
        query SearchPosts($query: String!) {
            posts(order: VOTES, search: $query, first: 5) {
                edges {
                    node {
                        id
                        name
                        tagline
                        url
                        votesCount
                        website
                    }
                }
            }
        }
        """
        resp = await client.post(
            "https://api.producthunt.com/v2/api/graphql",
            json={"query": graphql_query, "variables": {"query": query}},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            logger.warning("Product Hunt returned %d for query: %s", resp.status_code, query)
            return matches

        data = resp.json()
        edges = data.get("data", {}).get("posts", {}).get("edges", [])
        for edge in edges[:5]:
            node = edge.get("node", {})
            matches.append(PriorArtMatch(
                source="product_hunt",
                title=node.get("name", ""),
                url=node.get("url", ""),
                description=node.get("tagline", "") or "",
                match_signals={
                    "votes": node.get("votesCount", 0),
                    "website": node.get("website", ""),
                },
                search_query=query,
            ))
    except Exception:
        logger.warning("Product Hunt search failed for query: %s", query, exc_info=True)
    return matches


_SEARCH_FNS: dict[str, object] = {
    "github": _search_github,
    "npm": _search_npm,
    "pypi": _search_pypi,
    "product_hunt": _search_product_hunt,
}


# ── Scoring ──────────────────────────────────────────────────────

def _idea_text(unit: BuildableUnit) -> str:
    """Build text representation for embedding comparison."""
    return f"{unit.title} {unit.one_liner} {unit.problem[:200]}"


def _match_text(match: PriorArtMatch) -> str:
    """Build text representation for a match."""
    return f"{match.title} {match.description[:200]}"


def score_matches(unit: BuildableUnit, raw_matches: list[PriorArtMatch]) -> list[PriorArtMatch]:
    """Score matches by semantic similarity to the idea. Discard below 0.65."""
    if not raw_matches:
        return []

    idea_embedding = embed_text(_idea_text(unit))
    scored: list[PriorArtMatch] = []

    for match in raw_matches:
        match_embedding = embed_text(_match_text(match))
        sim = _cosine_similarity(idea_embedding, match_embedding)
        if sim >= 0.65:
            match.relevance_score = round(sim, 3)
            scored.append(match)

    scored.sort(key=lambda m: m.relevance_score, reverse=True)
    return scored


def determine_status(matches: list[PriorArtMatch]) -> str:
    """Determine prior art status from scored matches."""
    if not matches:
        return "clear"
    max_score = max(m.relevance_score for m in matches)
    if max_score >= 0.85:
        return "strong_match"
    if max_score >= 0.65:
        return "weak_match"
    return "clear"


# ── Orchestrator ─────────────────────────────────────────────────

async def _search_source(
    source: str,
    queries: list[str],
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    delay: float,
    **kwargs: object,
) -> list[PriorArtMatch]:
    """Search a single source with rate limiting."""
    search_fn = _SEARCH_FNS.get(source)
    if search_fn is None:
        return []

    all_matches: list[PriorArtMatch] = []
    seen_urls: set[str] = set()

    for query in queries:
        async with semaphore:
            results = await search_fn(query, client, **kwargs)
            for match in results:
                if match.url not in seen_urls:
                    seen_urls.add(match.url)
                    all_matches.append(match)
            if delay > 0:
                await asyncio.sleep(delay)

    return all_matches


async def check_prior_art_batch(
    units: list[BuildableUnit],
    *,
    dry_run: bool = False,
) -> list[PriorArtResult]:
    """Check prior art for a batch of buildable units."""
    results: list[PriorArtResult] = []

    # Build semaphores per source
    semaphores = {
        source: asyncio.Semaphore(limit)
        for source, (limit, _) in _RATE_LIMITS.items()
    }

    # Resolve GitHub token once
    gh_token = _resolve_github_token()
    gh_headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "max-idea-engine/0.1.0",
    }
    if gh_token:
        gh_headers["Authorization"] = f"Bearer {gh_token}"

    # Use neutral headers for the shared client; GitHub search overrides per-request
    shared_headers: dict[str, str] = {
        "User-Agent": "max-idea-engine/0.1.0",
    }

    async with httpx.AsyncClient(timeout=30, headers=shared_headers) as client:
        for unit in units:
            queries = build_search_queries(unit)
            sources = select_sources(unit)

            if dry_run:
                results.append(PriorArtResult(
                    buildable_unit_id=unit.id,
                    matches=[],
                    status="unchecked",
                ))
                continue

            # Search all sources concurrently for this unit
            tasks = []
            for source in sources:
                _, delay = _RATE_LIMITS.get(source, (3, 1.0))
                kwargs: dict[str, object] = {}
                if source == "github":
                    kwargs["extra_headers"] = gh_headers
                tasks.append(
                    _search_source(source, queries, client, semaphores[source], delay, **kwargs)
                )

            source_results = await asyncio.gather(*tasks)
            raw_matches: list[PriorArtMatch] = []
            for matches in source_results:
                raw_matches.extend(matches)

            # Score and filter
            scored = score_matches(unit, raw_matches)
            status = determine_status(scored)

            results.append(PriorArtResult(
                buildable_unit_id=unit.id,
                matches=scored,
                status=status,
            ))

    return results


def check_prior_art(
    units: list[BuildableUnit],
    *,
    dry_run: bool = False,
) -> list[PriorArtResult]:
    """Sync wrapper around check_prior_art_batch."""
    return asyncio.run(check_prior_art_batch(units, dry_run=dry_run))
