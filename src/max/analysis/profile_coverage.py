"""Coverage checks for profile watchlist and category terms."""

from __future__ import annotations

from dataclasses import dataclass, field

from max.profiles.schema import PipelineProfile
from max.store.db import Store

_WATCHLIST_PARAM_KEYS = {
    "categories",
    "filter_keywords",
    "keywords",
    "queries",
    "subreddits",
    "tags",
    "topics",
    "watchlist_terms",
}


@dataclass(frozen=True)
class ProfileCoverageTerm:
    """Stored signal coverage for one configured profile term."""

    term: str
    term_type: str
    total_count: int
    adapter_counts: dict[str, int]
    enabled_adapters: list[str]
    suggested_source_adapters: list[str]


@dataclass(frozen=True)
class ProfileCoverageReport:
    """Low-coverage signal terms for a profile."""

    profile_name: str
    domain: str
    low_coverage_threshold: int
    enabled_adapters: list[str]
    terms: list[ProfileCoverageTerm] = field(default_factory=list)


def compute_profile_coverage_gaps(
    profile: PipelineProfile,
    store: Store,
    *,
    low_coverage_threshold: int = 1,
) -> ProfileCoverageReport:
    """Return configured terms whose active stored signal coverage is below threshold.

    Terms come from enabled source watchlists/query-like params and the profile's
    domain categories. Counts are scoped to the enabled adapters associated with
    each term and match against signal tags, title, or content.
    """

    enabled_sources = [source for source in profile.sources if source.enabled]
    enabled_adapters = _dedupe([source.adapter for source in enabled_sources])
    term_adapters: dict[str, list[str]] = {}
    term_labels: dict[str, str] = {}
    term_types: dict[str, set[str]] = {}

    for source in enabled_sources:
        for term in _source_watchlist_terms(source):
            key = _term_key(term)
            term_labels.setdefault(key, term)
            term_types.setdefault(key, set()).add("watchlist")
            term_adapters.setdefault(key, [])
            if source.adapter not in term_adapters[key]:
                term_adapters[key].append(source.adapter)

    for category in profile.domain.categories:
        term = category.strip()
        if not term:
            continue
        key = _term_key(term)
        term_labels.setdefault(key, term)
        term_types.setdefault(key, set()).add("category")
        term_adapters.setdefault(key, [])
        for adapter in enabled_adapters:
            if adapter not in term_adapters[key]:
                term_adapters[key].append(adapter)

    gaps: list[ProfileCoverageTerm] = []
    for key in sorted(term_labels, key=lambda item: term_labels[item].lower()):
        adapters = term_adapters[key]
        adapter_counts = {
            adapter: count_active_signals_for_term(store, adapter=adapter, term=term_labels[key])
            for adapter in adapters
        }
        total_count = sum(adapter_counts.values())
        if total_count >= low_coverage_threshold:
            continue

        gaps.append(
            ProfileCoverageTerm(
                term=term_labels[key],
                term_type="+".join(sorted(term_types.get(key, {"watchlist"}))),
                total_count=total_count,
                adapter_counts=adapter_counts,
                enabled_adapters=adapters,
                suggested_source_adapters=[
                    adapter
                    for adapter in adapters
                    if adapter_counts.get(adapter, 0) < low_coverage_threshold
                ],
            )
        )

    return ProfileCoverageReport(
        profile_name=profile.name,
        domain=profile.domain.name,
        low_coverage_threshold=low_coverage_threshold,
        enabled_adapters=enabled_adapters,
        terms=gaps,
    )


def count_active_signals_for_term(store: Store, *, adapter: str, term: str) -> int:
    """Count active signals for an adapter whose tags, title, or content mention a term."""

    pattern = _like_pattern(term.strip().lower())
    row = store.conn.execute(
        """SELECT COUNT(*) AS count
           FROM signals
           WHERE archived_at IS NULL
             AND source_adapter = ?
             AND (
               lower(title) LIKE ? ESCAPE '\\'
               OR lower(content) LIKE ? ESCAPE '\\'
               OR lower(tags) LIKE ? ESCAPE '\\'
             )""",
        (adapter, pattern, pattern, pattern),
    ).fetchone()
    return int(row["count"] if row else 0)


def _source_watchlist_terms(source) -> list[str]:
    terms = list(source.watchlist)
    params = source.normalized_params
    for key in sorted(_WATCHLIST_PARAM_KEYS):
        value = params.get(key)
        if isinstance(value, list):
            terms.extend(item for item in value if isinstance(item, str))
    return _dedupe(term.strip() for term in terms if term.strip())


def _term_key(term: str) -> str:
    return term.strip().casefold()


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = str(value).casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(str(value))
    return deduped


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
