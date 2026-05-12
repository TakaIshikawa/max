"""Trello card import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

TRELLO_API = "https://api.trello.com/1"


class TrelloAdapter(SourceAdapter):
    def __init__(self, config: dict | None = None, *, key: str | None = None, token: str | None = None, api_url: str = TRELLO_API, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self.key = key if key is not None else os.getenv("TRELLO_API_KEY")
        self.token = token if token is not None else os.getenv("TRELLO_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "trello_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def board_ids(self) -> list[str]:
        return _strings(self._config.get("board_ids"))

    @property
    def list_ids(self) -> list[str]:
        return _strings(self._config.get("list_ids"))

    @property
    def labels(self) -> list[str]:
        return _strings(self._config.get("labels"))

    @property
    def include_closed(self) -> bool:
        return bool(self._config.get("include_closed", False))

    @property
    def updated_since(self) -> str | None:
        value = self._config.get("updated_since")
        return value if isinstance(value, str) and value else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.key and self.token):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            cards: list[dict[str, Any]] = []
            for board_id in self.board_ids:
                cards.extend(await self._get_cards(client, f"/boards/{board_id}/cards"))
            for list_id in self.list_ids:
                cards.extend(await self._get_cards(client, f"/lists/{list_id}/cards"))
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        label_filter = {label.lower() for label in self.labels}
        for card in cards:
            card_id = _text(card.get("id"))
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            names = [_text(label.get("name")) for label in card.get("labels", []) if isinstance(label, dict)]
            if label_filter and not label_filter.intersection({name.lower() for name in names}):
                continue
            if not self.include_closed and bool(card.get("closed")):
                continue
            signal = _trello_signal(card, self.name, names)
            signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _get_cards(self, client: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
        params = {"key": self.key, "token": self.token, "limit": 1000, "members": "true", "labels": "all", "actions": "updateCard:id,date", "filter": "all" if self.include_closed else "open"}
        if self.updated_since:
            params["since"] = self.updated_since
        try:
            response = await client.get(f"{self.api_url}{path}", params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Trello card fetch failed for %s", path, exc_info=True)
            return []
        return data if isinstance(data, list) else []


TrelloCardAdapter = TrelloAdapter


def _trello_signal(card: dict[str, Any], adapter_name: str, labels: list[str]) -> Signal:
    members = card.get("members") if isinstance(card.get("members"), list) else []
    actions = card.get("actions") if isinstance(card.get("actions"), list) else []
    updated_at = actions[0].get("date") if actions and isinstance(actions[0], dict) else card.get("dateLastActivity")
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(card.get("name")) or _text(card.get("id")),
        content=_text(card.get("desc"))[:1000],
        url=_text(card.get("url") or card.get("shortUrl")),
        author=", ".join(_text(member.get("fullName") or member.get("username")) for member in members if isinstance(member, dict)) or None,
        published_at=_parse_dt(card.get("dateLastActivity") or updated_at),
        tags=sorted({"trello", *labels} - {""})[:10],
        credibility=0.6,
        metadata={
            "trello_card_id": card.get("id"),
            "short_link": card.get("shortLink"),
            "list_id": card.get("idList"),
            "board_id": card.get("idBoard"),
            "closed": bool(card.get("closed")),
            "due": card.get("due"),
            "labels": labels,
            "members": [_text(member.get("username") or member.get("fullName")) for member in members if isinstance(member, dict)],
            "date_last_activity": card.get("dateLastActivity"),
            "last_action_at": updated_at,
        },
    )


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
