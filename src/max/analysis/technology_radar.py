"""Technology radar analysis for stack trend detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


LANGUAGES = frozenset(
    {
        "C#",
        "C++",
        "Go",
        "Java",
        "JavaScript",
        "Kotlin",
        "PHP",
        "Python",
        "Ruby",
        "Rust",
        "Scala",
        "Swift",
        "TypeScript",
    }
)

FRAMEWORKS = frozenset(
    {
        "Angular",
        "Django",
        "FastAPI",
        "Flask",
        "Laravel",
        "Next.js",
        "Phoenix",
        "Rails",
        "React",
        "Remix",
        "Svelte",
        "Vue",
    }
)

TOOLS = frozenset(
    {
        "Bun",
        "Docker",
        "GitHub Actions",
        "Kubernetes",
        "Playwright",
        "PostgreSQL",
        "Redis",
        "Terraform",
        "Vite",
        "Webpack",
    }
)

PLATFORMS = frozenset(
    {
        "AWS",
        "Azure",
        "Cloudflare",
        "Firebase",
        "GCP",
        "Heroku",
        "Netlify",
        "Supabase",
        "Vercel",
    }
)

_QUADRANT_KEYWORDS: tuple[tuple[str, frozenset[str]], ...] = (
    ("languages", LANGUAGES),
    ("frameworks", FRAMEWORKS),
    ("tools", TOOLS),
    ("platforms", PLATFORMS),
)

_ALIASES = {
    "amazon web services": "AWS",
    "c sharp": "C#",
    "cplusplus": "C++",
    "github action": "GitHub Actions",
    "google cloud": "GCP",
    "js": "JavaScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "postgres": "PostgreSQL",
    "py": "Python",
    "ts": "TypeScript",
}


@dataclass(frozen=True)
class TechnologyEntry:
    name: str
    ring: str
    quadrant: str
    signal_count: int
    momentum: float
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ring": self.ring,
            "quadrant": self.quadrant,
            "signal_count": self.signal_count,
            "momentum": self.momentum,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


@dataclass
class TechnologyRadar:
    entries: list[TechnologyEntry]
    generated_at: str
    signal_window_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "generated_at": self.generated_at,
            "signal_window_days": self.signal_window_days,
        }


class TechnologyRadarAnalyzer:
    """Analyze technology adoption trends from in-memory signal dictionaries."""

    def __init__(
        self,
        *,
        signal_window_days: int = 90,
        adopt_threshold: float = 0.7,
        trial_threshold: float = 0.4,
        assess_threshold: float = 0.1,
    ) -> None:
        if signal_window_days < 1:
            raise ValueError("signal_window_days must be at least 1")
        thresholds = (adopt_threshold, trial_threshold, assess_threshold)
        if any(threshold < 0 or threshold > 1 for threshold in thresholds):
            raise ValueError("thresholds must be between 0 and 1")
        if not adopt_threshold >= trial_threshold >= assess_threshold:
            raise ValueError("thresholds must be ordered adopt >= trial >= assess")

        self.signal_window_days = signal_window_days
        self.adopt_threshold = float(adopt_threshold)
        self.trial_threshold = float(trial_threshold)
        self.assess_threshold = float(assess_threshold)
        self._keyword_index = _build_keyword_index()

    def analyze(self, signals: list[dict[str, Any]]) -> TechnologyRadar:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=self.signal_window_days)
        technology_hits: dict[tuple[str, str], list[datetime]] = {}
        included_signals = 0

        for signal in signals:
            timestamp = _parse_optional_timestamp(
                signal.get("published_at")
                or signal.get("fetched_at")
                or signal.get("created_at")
            )
            timestamp = timestamp or now
            if timestamp < window_start:
                continue

            included_signals += 1
            text = _signal_text(signal)
            for name, quadrant in set(self._extract_technologies(text)):
                technology_hits.setdefault((name, quadrant), []).append(timestamp)

        entries = [
            TechnologyEntry(
                name=name,
                ring=self._classify_ring(len(timestamps), momentum, included_signals),
                quadrant=quadrant,
                signal_count=len(timestamps),
                momentum=momentum,
                first_seen=min(timestamps).isoformat(),
                last_seen=max(timestamps).isoformat(),
            )
            for (name, quadrant), timestamps in technology_hits.items()
            for momentum in [self._calculate_momentum(timestamps)]
        ]
        entries.sort(
            key=lambda entry: (
                entry.quadrant,
                _ring_rank(entry.ring),
                -entry.signal_count,
                -entry.momentum,
                entry.name.lower(),
            )
        )
        return TechnologyRadar(
            entries=entries,
            generated_at=now.isoformat(),
            signal_window_days=self.signal_window_days,
        )

    def _extract_technologies(self, text: str) -> list[tuple[str, str]]:
        normalized = text.lower()
        matches: set[tuple[str, str]] = set()
        for keyword, canonical in self._keyword_index.items():
            if _contains_keyword(normalized, keyword):
                matches.add(canonical)
        return sorted(matches, key=lambda item: (item[1], item[0].lower()))

    def _calculate_momentum(self, timestamps: list[datetime]) -> float:
        if len(timestamps) < 2:
            return 0.0

        normalized = [_ensure_aware_utc(timestamp) for timestamp in timestamps]
        newest = max(normalized)
        split = newest - timedelta(days=self.signal_window_days / 2)
        recent_count = sum(timestamp >= split for timestamp in normalized)
        older_count = len(normalized) - recent_count
        if recent_count + older_count == 0:
            return 0.0
        return round((recent_count - older_count) / (recent_count + older_count), 4)

    def _classify_ring(self, count: int, momentum: float, total_signals: int) -> str:
        if count <= 0 or total_signals <= 0:
            return "hold"

        share = count / total_signals
        if share >= self.adopt_threshold and momentum >= -0.5:
            return "adopt"
        if share >= self.trial_threshold and momentum >= -0.75:
            return "trial"
        if share >= self.assess_threshold or momentum > 0:
            return "assess"
        return "hold"


def render_radar_markdown(radar: TechnologyRadar) -> str:
    lines = [
        "# Technology Radar",
        "",
        f"Generated: {radar.generated_at}",
        f"Signal window: {radar.signal_window_days} days",
        "",
        "| Quadrant | Ring | Technology | Signals | Momentum | First seen | Last seen |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]

    if not radar.entries:
        lines.append("| - | - | No technologies detected | 0 | 0.00 | - | - |")
        return "\n".join(lines)

    for entry in radar.entries:
        lines.append(
            "| "
            f"{entry.quadrant} | "
            f"{entry.ring} | "
            f"{entry.name} | "
            f"{entry.signal_count} | "
            f"{entry.momentum:.2f} | "
            f"{entry.first_seen} | "
            f"{entry.last_seen} |"
        )
    return "\n".join(lines)


def _build_keyword_index() -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for quadrant, keywords in _QUADRANT_KEYWORDS:
        for keyword in keywords:
            index[keyword.lower()] = (keyword, quadrant)
    for alias, canonical in _ALIASES.items():
        quadrant = _quadrant_for(canonical)
        if quadrant:
            index[alias] = (canonical, quadrant)
    return index


def _quadrant_for(name: str) -> str | None:
    for quadrant, keywords in _QUADRANT_KEYWORDS:
        if name in keywords:
            return quadrant
    return None


def _contains_keyword(text: str, keyword: str) -> bool:
    escaped = re.escape(keyword)
    pattern = rf"(?<![a-z0-9+#.]){escaped}(?![a-z0-9+#])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _signal_text(signal: dict[str, Any]) -> str:
    tags = signal.get("tags") or []
    if isinstance(tags, str):
        tags_text = tags
    else:
        tags_text = " ".join(str(tag) for tag in tags)
    return " ".join(
        str(part)
        for part in (
            signal.get("title") or "",
            signal.get("content") or "",
            signal.get("summary") or "",
            tags_text,
        )
        if part
    )


def _parse_optional_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_aware_utc(value)
    if not value:
        return None
    return _ensure_aware_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ring_rank(ring: str) -> int:
    return {"adopt": 0, "trial": 1, "assess": 2, "hold": 3}.get(ring, 4)
