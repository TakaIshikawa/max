"""Stack Overflow question activity source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class StackOverflowQuestionActivityAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "stackoverflow_question_activity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def api_url(self) -> str:
        return str(self._config.get("stackexchange_api_url") or "https://api.stackexchange.com/2.3").strip().rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        params = {
            "site": self._config.get("site") or "stackoverflow",
            "pagesize": int(self._config.get("max_questions") or limit),
            "order": "desc",
            "sort": "activity",
            "filter": "default",
        }
        tags = _strings(self._config.get("tags"))
        if tags:
            params["tagged"] = ";".join(tags)
        if self._config.get("query"):
            params["intitle"] = str(self._config["query"])
        if self._config.get("min_score") is not None:
            params["min"] = int(self._config["min_score"])
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.api_url}/search/advanced", params=params)
        if response.status_code >= 400:
            return []
        items = response.json().get("items", [])
        return [_signal(i) for i in items[:limit] if _num(i.get("score")) >= _num(self._config.get("min_score"))]


def _signal(item: dict[str, Any]) -> Signal:
    qid = item.get("question_id") or item.get("id") or item.get("link")
    tags = [str(t) for t in item.get("tags") or []]
    accepted = bool(item.get("accepted_answer_id") or item.get("is_answered"))
    return Signal(
        id=_id("so-question", qid),
        source_type=SignalSourceType.FORUM,
        source_adapter="stackoverflow_question_activity",
        title=str(item.get("title") or f"Stack Overflow question {qid}"),
        content=f"{item.get('answer_count', 0)} answers, score {item.get('score', 0)}, {'accepted' if accepted else 'unresolved'}.",
        url=str(item.get("link") or ""),
        published_at=_dt(item.get("creation_date") or item.get("last_activity_date")),
        tags=["stackoverflow", *tags],
        credibility=min(max(_num(item.get("score")) / 100, 0.1), 1.0),
        metadata={
            "question_id": qid,
            "accepted_answer_id": item.get("accepted_answer_id"),
            "has_accepted_answer": accepted,
            "resolution_status": "accepted" if accepted else "unresolved",
            "answer_count": int(_num(item.get("answer_count"))),
            "score": int(_num(item.get("score"))),
            "view_count": int(_num(item.get("view_count"))),
            "tags": tags,
            "last_activity_date": item.get("last_activity_date"),
            "source_url": item.get("link") or "",
            "signal_role": "problem" if not accepted else "market",
        },
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _dt(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
