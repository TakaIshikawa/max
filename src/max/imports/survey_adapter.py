"""Developer survey source adapter for sentiment signals.

Ingests structured survey results from sources like Stack Overflow Developer
Survey and JetBrains Developer Ecosystem Survey.  Parses CSV and JSON datasets,
extracts language popularity rankings, salary data, and tool satisfaction
scores.  Provides normalized signal output for trend comparison.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

# Column name mappings for common survey formats.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "language": ["language", "lang", "programming_language", "tech", "technology"],
    "rank": ["rank", "position", "popularity_rank"],
    "popularity": ["popularity", "usage_pct", "usage_percent", "pct", "share"],
    "satisfaction": ["satisfaction", "satisfaction_pct", "loved_pct", "approval"],
    "salary": ["salary", "median_salary", "avg_salary", "compensation"],
    "respondents": ["respondents", "responses", "n", "count", "sample_size"],
}


def _resolve_column(headers: list[str], field: str) -> str | None:
    """Find the first matching header for a logical field name."""
    aliases = _COLUMN_ALIASES.get(field, [field])
    lower_headers = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        if alias in lower_headers:
            return lower_headers[alias]
    return None


def _safe_float(value: str | int | float | None) -> float | None:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("%").replace(",", ""))
    except (ValueError, TypeError):
        return None


def _normalize_score(value: float | None, max_val: float = 100.0) -> float:
    """Normalize a numeric score to 0.0–1.0 range."""
    if value is None:
        return 0.5
    return max(0.0, min(value / max_val, 1.0))


def _build_tags(language: str, survey_source: str, category: str) -> list[str]:
    """Build tags for a survey signal entry."""
    tags: set[str] = {"survey", survey_source}
    if category:
        tags.add(category)
    lang_lower = language.lower().strip()
    lang_map = {
        "typescript": "typescript",
        "javascript": "typescript",
        "python": "python",
        "rust": "rust",
        "go": "go",
        "golang": "go",
        "java": "java",
        "c#": "csharp",
        "c++": "cpp",
        "kotlin": "kotlin",
        "swift": "swift",
    }
    mapped = lang_map.get(lang_lower)
    if mapped:
        tags.add(mapped)
    return sorted(tags)


def parse_csv_survey(content: str, *, survey_source: str = "survey") -> list[dict]:
    """Parse a CSV survey dataset into normalized row dicts.

    Returns a list of dicts with keys: language, rank, popularity,
    satisfaction, salary, respondents.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return []

    headers = list(reader.fieldnames)
    col_language = _resolve_column(headers, "language")
    col_rank = _resolve_column(headers, "rank")
    col_popularity = _resolve_column(headers, "popularity")
    col_satisfaction = _resolve_column(headers, "satisfaction")
    col_salary = _resolve_column(headers, "salary")
    col_respondents = _resolve_column(headers, "respondents")

    if not col_language:
        logger.warning("CSV survey missing language column; headers=%s", headers)
        return []

    rows: list[dict] = []
    for i, row in enumerate(reader):
        language = (row.get(col_language) or "").strip()
        if not language:
            continue

        entry: dict = {
            "language": language,
            "rank": int(_safe_float(row.get(col_rank)) or (i + 1)),
            "popularity": _safe_float(row.get(col_popularity) if col_popularity else None),
            "satisfaction": _safe_float(row.get(col_satisfaction) if col_satisfaction else None),
            "salary": _safe_float(row.get(col_salary) if col_salary else None),
            "respondents": int(_safe_float(row.get(col_respondents) if col_respondents else None) or 0),
            "survey_source": survey_source,
        }
        rows.append(entry)

    return rows


def parse_json_survey(content: str, *, survey_source: str = "survey") -> list[dict]:
    """Parse a JSON survey dataset into normalized row dicts.

    Accepts either a JSON array of objects or an object with a ``results``
    or ``data`` key containing the array.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in survey data")
        return []

    if isinstance(data, dict):
        items = data.get("results") or data.get("data") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        return []

    rows: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        language = str(item.get("language") or item.get("tech") or item.get("name") or "").strip()
        if not language:
            continue

        entry: dict = {
            "language": language,
            "rank": int(item.get("rank", item.get("position", i + 1))),
            "popularity": _safe_float(item.get("popularity") or item.get("usage_pct")),
            "satisfaction": _safe_float(item.get("satisfaction") or item.get("loved_pct")),
            "salary": _safe_float(item.get("salary") or item.get("median_salary")),
            "respondents": int(_safe_float(item.get("respondents") or item.get("count")) or 0),
            "survey_source": survey_source,
        }
        rows.append(entry)

    return rows


class SurveyAdapter(SourceAdapter):
    """Ingests developer survey data from CSV/JSON files or inline config.

    Parses language popularity rankings, tool satisfaction scores, and salary
    data.  Normalizes across different survey formats for cross-source trend
    comparison.

    Config options:
        files: list of file paths to survey CSV/JSON files
        data: inline list of survey entries (JSON format)
        survey_source: identifier for the survey (default: "survey")
    """

    @property
    def name(self) -> str:
        return "survey_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def survey_source(self) -> str:
        s = self._config.get("survey_source", "survey")
        return s if isinstance(s, str) else "survey"

    @property
    def files(self) -> list[str]:
        f = self._config.get("files", [])
        return f if isinstance(f, list) else []

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        rows: list[dict] = []

        # Parse from configured file paths
        for file_path in self.files:
            try:
                path = Path(file_path)
                content = path.read_text(encoding="utf-8")
                if path.suffix.lower() == ".csv":
                    rows.extend(parse_csv_survey(content, survey_source=self.survey_source))
                elif path.suffix.lower() in (".json", ".jsonl"):
                    rows.extend(parse_json_survey(content, survey_source=self.survey_source))
                else:
                    logger.warning("Unsupported survey file format: %s", path.suffix)
            except Exception:
                logger.warning("Failed to read survey file: %s", file_path, exc_info=True)

        # Parse from inline config data
        inline_data = self._config.get("data")
        if isinstance(inline_data, list):
            for item in inline_data:
                if isinstance(item, dict):
                    language = str(item.get("language", "")).strip()
                    if not language:
                        continue
                    rows.append({
                        "language": language,
                        "rank": int(item.get("rank", len(rows) + 1)),
                        "popularity": _safe_float(item.get("popularity")),
                        "satisfaction": _safe_float(item.get("satisfaction")),
                        "salary": _safe_float(item.get("salary")),
                        "respondents": int(_safe_float(item.get("respondents")) or 0),
                        "survey_source": self.survey_source,
                    })

        signals = self._rows_to_signals(rows)
        return signals[:limit]

    def _rows_to_signals(self, rows: list[dict]) -> list[Signal]:
        """Convert parsed survey rows into Signal objects."""
        signals: list[Signal] = []
        seen: set[str] = set()

        for row in rows:
            language = row["language"]
            source = row.get("survey_source", self.survey_source)
            key = f"{source}:{language}"
            if key in seen:
                continue
            seen.add(key)

            popularity = row.get("popularity")
            satisfaction = row.get("satisfaction")
            salary = row.get("salary")
            rank = row.get("rank", 0)

            parts: list[str] = [f"{language} (rank #{rank})"]
            if popularity is not None:
                parts.append(f"popularity: {popularity:.1f}%")
            if satisfaction is not None:
                parts.append(f"satisfaction: {satisfaction:.1f}%")
            if salary is not None:
                parts.append(f"median salary: ${salary:,.0f}")
            content = " | ".join(parts)

            # Credibility based on respondent count
            respondents = row.get("respondents", 0)
            credibility = _normalize_score(respondents, max_val=100_000)

            category = "language_ranking"
            if satisfaction is not None:
                category = "satisfaction"
            if salary is not None:
                category = "salary"

            signals.append(
                Signal(
                    source_type=SignalSourceType.SURVEY,
                    source_adapter=self.name,
                    title=f"{source}: {language}",
                    content=content[:500],
                    url="",
                    tags=_build_tags(language, source, category),
                    credibility=credibility,
                    metadata={
                        "language": language,
                        "rank": rank,
                        "popularity": popularity,
                        "satisfaction": satisfaction,
                        "salary": salary,
                        "respondents": respondents,
                        "survey_source": source,
                    },
                )
            )

        return signals
