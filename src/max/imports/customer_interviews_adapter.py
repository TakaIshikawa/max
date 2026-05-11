"""Customer interview notes import adapter."""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_ALIASES: dict[str, list[str]] = {
    "interviewee": ["interviewee", "name", "customer", "participant", "contact"],
    "role": ["role", "title", "job_title", "persona"],
    "company_segment": ["company_segment", "segment", "company_size", "market_segment"],
    "pain": ["pain", "pain_point", "problem", "challenge", "need"],
    "current_workaround": ["current_workaround", "workaround", "current_solution", "alternative"],
    "willingness_to_pay": ["willingness_to_pay", "wtp", "budget", "price", "willing_to_pay"],
    "quote": ["quote", "verbatim", "customer_quote", "evidence", "note"],
    "evidence_strength": ["evidence_strength", "strength", "confidence", "score"],
    "domain": ["domain", "company_domain", "url", "website"],
}


def _resolve(headers: list[str], field: str) -> str | None:
    lower = {header.strip().lower(): header for header in headers}
    for alias in _ALIASES.get(field, [field]):
        if alias in lower:
            return lower[alias]
    return None


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float(value: object, default: float = 0.5) -> float:
    try:
        parsed = float(str(value).strip().rstrip("%").replace(",", ""))
    except (TypeError, ValueError):
        return default
    if parsed > 1:
        parsed = parsed / 100
    return max(0.0, min(parsed, 1.0))


def _normalize_row(item: dict, *, interview_source: str, default_domain: str = "") -> dict | None:
    row = {
        field: _text(item.get(field) or next((_text(item.get(alias)) for alias in aliases if _text(item.get(alias))), ""))
        for field, aliases in _ALIASES.items()
    }
    pain = row["pain"]
    quote = row["quote"]
    if not pain and not quote:
        return None
    row["interview_source"] = interview_source
    row["domain"] = row["domain"] or default_domain
    row["evidence_strength"] = row["evidence_strength"] or "0.6"
    return row


def parse_csv_interviews(
    content: str,
    *,
    interview_source: str = "customer_interview",
    default_domain: str = "",
) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return []
    columns = {field: _resolve(list(reader.fieldnames), field) for field in _ALIASES}
    rows: list[dict] = []
    for raw in reader:
        item = {field: raw.get(column, "") if column else "" for field, column in columns.items()}
        normalized = _normalize_row(
            item,
            interview_source=interview_source,
            default_domain=default_domain,
        )
        if normalized:
            rows.append(normalized)
    return rows


def parse_json_interviews(
    content: str,
    *,
    interview_source: str = "customer_interview",
    default_domain: str = "",
) -> list[dict]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in customer interview data")
        return []
    return normalize_interview_items(data, interview_source=interview_source, default_domain=default_domain)


def normalize_interview_items(
    data: object,
    *,
    interview_source: str = "customer_interview",
    default_domain: str = "",
) -> list[dict]:
    if isinstance(data, dict):
        items = data.get("interviews") or data.get("data") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        return []

    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_row(
            item,
            interview_source=interview_source,
            default_domain=default_domain,
        )
        if normalized:
            rows.append(normalized)
    return rows


class CustomerInterviewsAdapter(SourceAdapter):
    """Convert structured customer interview notes into survey signals."""

    @property
    def name(self) -> str:
        return "customer_interviews"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def interview_source(self) -> str:
        value = self._config.get("interview_source", "customer_interview")
        return value if isinstance(value, str) and value.strip() else "customer_interview"

    @property
    def files(self) -> list[str]:
        value = self._config.get("files", [])
        return value if isinstance(value, list) else []

    @property
    def tags(self) -> list[str]:
        value = self._config.get("tags", [])
        return sorted({_text(tag).lower() for tag in value if _text(tag)})

    @property
    def default_domain(self) -> str:
        value = self._config.get("default_domain", "")
        return value if isinstance(value, str) else ""

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        rows: list[dict] = []
        for file_path in self.files:
            try:
                path = Path(file_path)
                content = path.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Failed to read customer interview file: %s", file_path, exc_info=True)
                continue
            if path.suffix.lower() == ".csv":
                rows.extend(
                    parse_csv_interviews(
                        content,
                        interview_source=self.interview_source,
                        default_domain=self.default_domain,
                    )
                )
            elif path.suffix.lower() in {".json", ".jsonl"}:
                rows.extend(
                    parse_json_interviews(
                        content,
                        interview_source=self.interview_source,
                        default_domain=self.default_domain,
                    )
                )

        rows.extend(
            normalize_interview_items(
                self._config.get("data"),
                interview_source=self.interview_source,
                default_domain=self.default_domain,
            )
        )
        return self._rows_to_signals(rows)[:limit]

    def _rows_to_signals(self, rows: list[dict]) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            pain = row["pain"]
            quote = row["quote"]
            key = (row.get("interviewee", ""), pain, quote)
            if key in seen:
                continue
            seen.add(key)

            role = row.get("role", "")
            segment = row.get("company_segment", "")
            title_parts = [part for part in [role or row.get("interviewee", ""), segment, pain[:80]] if part]
            content_parts = [
                f"Pain: {pain}" if pain else "",
                f"Workaround: {row['current_workaround']}" if row["current_workaround"] else "",
                f"Willingness to pay: {row['willingness_to_pay']}" if row["willingness_to_pay"] else "",
                f"Quote: {quote}" if quote else "",
            ]
            tags = {"customer_interview", row["interview_source"], *self.tags}
            if role:
                tags.add(role.lower().replace(" ", "_"))
            if segment:
                tags.add(segment.lower().replace(" ", "_"))

            signals.append(
                Signal(
                    source_type=SignalSourceType.SURVEY,
                    source_adapter=self.name,
                    title=" | ".join(title_parts)[:160] or "Customer interview signal",
                    content="\n".join(part for part in content_parts if part)[:1000],
                    url=row.get("domain", ""),
                    author=row.get("interviewee") or None,
                    tags=sorted(tags),
                    credibility=_float(row.get("evidence_strength"), 0.6),
                    metadata={
                        "interviewee": row.get("interviewee", ""),
                        "role": role,
                        "company_segment": segment,
                        "pain": pain,
                        "current_workaround": row.get("current_workaround", ""),
                        "willingness_to_pay": row.get("willingness_to_pay", ""),
                        "quote": quote,
                        "evidence_strength": row.get("evidence_strength", ""),
                        "interview_source": row.get("interview_source", self.interview_source),
                        "domain": row.get("domain", ""),
                    },
                )
            )
        return signals
