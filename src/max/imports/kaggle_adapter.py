"""Kaggle source adapter for dataset popularity and competition signals.

Collects dataset popularity and competition signals from the Kaggle API.
Fetches trending datasets, competition metadata, and kernel activity.
Extracts download counts, vote counts, tags, and file sizes to identify
data science and ML trends.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

KAGGLE_API = "https://www.kaggle.com/api/v1"

_DEFAULT_CATEGORIES = ["featured", "research", "playground"]


def _get_api_token() -> tuple[str | None, str | None]:
    """Resolve Kaggle API credentials from env or vault.

    Returns (username, key) tuple.
    """
    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    if username and key:
        return username, key
    try:
        u_result = subprocess.run(
            ["vault", "get", "kaggle/username"],
            capture_output=True, text=True, timeout=5,
        )
        k_result = subprocess.run(
            ["vault", "get", "kaggle/key"],
            capture_output=True, text=True, timeout=5,
        )
        if u_result.returncode == 0 and k_result.returncode == 0:
            u = u_result.stdout.strip()
            k = k_result.stdout.strip()
            if u and k:
                return u, k
    except Exception:
        pass
    return None, None


def _parse_dt(s: str | None) -> datetime | None:
    """Parse datetime string from Kaggle API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_tags(raw_tags: list[str] | None, source: str) -> list[str]:
    """Build normalized tags from Kaggle dataset/competition tags."""
    tags: set[str] = {"kaggle", source}
    if raw_tags:
        for tag in raw_tags:
            if isinstance(tag, str) and tag.strip():
                tags.add(tag.strip().lower())
    return sorted(tags)


class KaggleAdapter(SourceAdapter):
    """Fetches datasets and competitions from the Kaggle API.

    Extracts download counts, votes, tags, and competition deadlines.
    Handles API token authentication and pagination via ``fetch_with_retry``.

    Config options:
        categories: list of competition categories to search
        search: search query string for datasets
        sort_by: sort order for datasets (hottest, votes, updated, active)
    """

    @property
    def name(self) -> str:
        return "kaggle_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def search_query(self) -> str | None:
        q = self._config.get("search")
        return q if isinstance(q, str) else None

    @property
    def sort_by(self) -> str:
        s = self._config.get("sort_by", "hottest")
        return s if isinstance(s, str) else "hottest"

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        username, key = _get_api_token()

        auth = httpx.BasicAuth(username, key) if username and key else None

        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            # Fetch datasets
            dataset_signals = await self._fetch_datasets(client, seen, limit)
            signals.extend(dataset_signals)

            # Fetch competitions if room
            remaining = limit - len(signals)
            if remaining > 0:
                comp_signals = await self._fetch_competitions(
                    client, seen, remaining,
                )
                signals.extend(comp_signals)

        return signals[:limit]

    async def _fetch_datasets(
        self, client: httpx.AsyncClient, seen: set[str], limit: int,
    ) -> list[Signal]:
        """Fetch trending/searched datasets from Kaggle."""
        signals: list[Signal] = []
        params: dict = {
            "sortBy": self.sort_by,
            "page": 1,
            "pageSize": min(limit, 20),
        }
        if self.search_query:
            params["search"] = self.search_query

        try:
            resp = await fetch_with_retry(
                f"{KAGGLE_API}/datasets/list",
                client,
                adapter_name=self.name,
                params=params,
            )
            data = resp.json()
        except Exception:
            logger.warning("Kaggle datasets fetch failed", exc_info=True)
            return signals

        items = data if isinstance(data, list) else data.get("datasets", [])
        for ds in items:
            sig = self._dataset_to_signal(ds, seen)
            if sig:
                signals.append(sig)
                if len(signals) >= limit:
                    break

        return signals

    async def _fetch_competitions(
        self, client: httpx.AsyncClient, seen: set[str], limit: int,
    ) -> list[Signal]:
        """Fetch competitions from Kaggle."""
        signals: list[Signal] = []

        for category in self.categories:
            if len(signals) >= limit:
                break

            params: dict = {
                "category": category,
                "page": 1,
                "pageSize": min(limit - len(signals), 20),
            }

            try:
                resp = await fetch_with_retry(
                    f"{KAGGLE_API}/competitions/list",
                    client,
                    adapter_name=self.name,
                    params=params,
                )
                data = resp.json()
            except Exception:
                logger.warning(
                    "Kaggle competitions fetch failed: %s", category,
                    exc_info=True,
                )
                continue

            items = data if isinstance(data, list) else data.get("competitions", [])
            for comp in items:
                sig = self._competition_to_signal(comp, seen, category)
                if sig:
                    signals.append(sig)
                    if len(signals) >= limit:
                        break

        return signals

    def _dataset_to_signal(
        self, ds: dict, seen: set[str],
    ) -> Signal | None:
        """Convert a Kaggle dataset dict to a Signal."""
        ref = ds.get("ref") or ds.get("id", "")
        if not ref or ref in seen:
            return None
        seen.add(ref)

        raw_tags = ds.get("tags", [])
        tag_names = []
        for t in raw_tags:
            if isinstance(t, str):
                tag_names.append(t)
            elif isinstance(t, dict):
                tag_names.append(t.get("name", ""))

        return Signal(
            source_type=SignalSourceType.TRENDING,
            source_adapter=self.name,
            title=ds.get("title") or ref,
            content=(ds.get("subtitle") or ds.get("description") or ref)[:500],
            url=f"https://www.kaggle.com/datasets/{ref}",
            author=ds.get("ownerName") or ds.get("creatorName"),
            published_at=_parse_dt(ds.get("lastUpdated") or ds.get("creationDate")),
            tags=_build_tags(tag_names, "dataset"),
            credibility=0.5,
            metadata={
                "kind": "dataset",
                "download_count": ds.get("downloadCount", 0),
                "vote_count": ds.get("voteCount", 0),
                "view_count": ds.get("viewCount", 0),
                "total_bytes": ds.get("totalBytes", 0),
                "usability_rating": ds.get("usabilityRating", 0.0),
                "file_count": ds.get("fileCount", 0),
                "license": ds.get("licenseName"),
                "tags": tag_names,
            },
        )

    def _competition_to_signal(
        self, comp: dict, seen: set[str], category: str,
    ) -> Signal | None:
        """Convert a Kaggle competition dict to a Signal."""
        ref = comp.get("ref") or comp.get("id", "")
        if not ref or ref in seen:
            return None
        seen.add(ref)

        raw_tags = comp.get("tags", [])
        tag_names = []
        for t in raw_tags:
            if isinstance(t, str):
                tag_names.append(t)
            elif isinstance(t, dict):
                tag_names.append(t.get("name", ""))

        return Signal(
            source_type=SignalSourceType.TRENDING,
            source_adapter=self.name,
            title=comp.get("title") or ref,
            content=(comp.get("description") or ref)[:500],
            url=f"https://www.kaggle.com/competitions/{ref}",
            author=comp.get("organizationName"),
            published_at=_parse_dt(comp.get("enabledDate")),
            tags=_build_tags(tag_names, "competition"),
            credibility=0.6,
            metadata={
                "kind": "competition",
                "category": category,
                "deadline": comp.get("deadline"),
                "reward": comp.get("reward"),
                "team_count": comp.get("teamCount", 0),
                "max_team_size": comp.get("maxTeamSize"),
                "evaluation_metric": comp.get("evaluationMetric"),
                "is_kernels_submit_enabled": comp.get("isKernelsSubmitEnabled", False),
                "tags": tag_names,
            },
        )
