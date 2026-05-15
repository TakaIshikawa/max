"""HubSpot forms import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
HUBSPOT_API = "https://api.hubapi.com"


class HubSpotFormsAdapter(SourceAdapter):
    """Fetch HubSpot form definitions and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        access_token: str | None = None,
        private_app_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            or access_token
            or private_app_token
            or _optional(self._config.get("token"))
            or _optional(self._config.get("access_token"))
            or _optional(self._config.get("private_app_token"))
            or os.getenv("HUBSPOT_ACCESS_TOKEN")
            or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or os.getenv("HUBSPOT_API_URL") or HUBSPOT_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_forms_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=50, maximum=100)

    @property
    def archived(self) -> bool:
        return _bool(self._config.get("archived"), default=False)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            forms = await self._fetch_forms(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for form in forms:
            signal = _form_signal(form, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_forms(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        forms: list[dict[str, Any]] = []
        after: str | None = None
        while len(forms) < limit:
            body = await self._get_forms(client, limit=min(self.page_size, limit - len(forms)), after=after)
            results = body.get("results") or body.get("forms")
            if not isinstance(results, list) or not results:
                break
            forms.extend(item for item in results if isinstance(item, dict))
            after = _next_after(body)
            if not after:
                break
        return forms[:limit]

    async def _get_forms(self, client: httpx.AsyncClient, *, limit: int, after: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "archived": str(self.archived).lower()}
        if after:
            params["after"] = after
        try:
            response = await client.get(
                f"{self.api_url}/marketing/v3/forms",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-forms-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot forms fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


HubSpotFormAdapter = HubSpotFormsAdapter


def _form_signal(form: dict[str, Any], *, adapter_name: str, seen: set[str]) -> Signal | None:
    form_id = _optional(form.get("id") or form.get("guid"))
    if not form_id:
        return None
    signal_id = f"hubspot-form:{form_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    name = _text(form.get("name"))
    form_type = _text(form.get("formType") or form.get("type"))
    archived = _bool_or_none(form.get("archived"))
    published = _published(form)
    labels = _field_labels(form)
    submit_actions = _submit_actions(form)
    created_at = form.get("createdAt") or form.get("created_at")
    updated_at = form.get("updatedAt") or form.get("updated_at")
    portal_id = form.get("portalId") or form.get("portal_id")

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=name or f"HubSpot form {form_id}",
        content=_content(name=name, form_type=form_type, archived=archived, published=published, labels=labels, submit_actions=submit_actions, portal_id=portal_id),
        url=_text(form.get("url") or form.get("previewUrl")),
        author=None,
        published_at=_parse_dt(updated_at) or _parse_dt(created_at),
        tags=sorted({"hubspot", "form", form_type.lower(), "archived" if archived else "active", "published" if published else "unpublished"} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "market",
            "form_id": form_id,
            "name": name or None,
            "form_type": form_type or None,
            "archived": archived,
            "published": published,
            "field_labels": labels,
            "submit_actions": submit_actions,
            "created_at": created_at,
            "updated_at": updated_at,
            "portal_id": portal_id,
            "raw": form,
        },
    )


def _field_labels(form: dict[str, Any]) -> list[str]:
    labels: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            label = _text(value.get("label") or value.get("name"))
            if label:
                labels.append(label)
            for nested_key in ("fields", "fieldGroups", "dependentFields", "dependentFieldFilters"):
                collect(value.get(nested_key))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(form.get("fieldGroups") or form.get("fields") or form.get("formFieldGroups"))
    return list(dict.fromkeys(labels))


def _submit_actions(form: dict[str, Any]) -> list[str]:
    actions = form.get("submitActions") or form.get("submit_actions") or form.get("followUp")
    if not isinstance(actions, list):
        actions = [actions] if isinstance(actions, dict) else []
    summaries: list[str] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = _text(action.get("type") or action.get("actionType"))
        value = _text(action.get("value") or action.get("url") or action.get("message"))
        summaries.append(": ".join(item for item in (action_type, value) if item))
    return [summary for summary in summaries if summary]


def _published(form: dict[str, Any]) -> bool | None:
    for key in ("published", "isPublished"):
        if isinstance(form.get(key), bool):
            return form[key]
    if form.get("publishedAt"):
        return True
    return None


def _content(*, name: str, form_type: str, archived: bool | None, published: bool | None, labels: list[str], submit_actions: list[str], portal_id: object) -> str:
    parts = ["HubSpot form"]
    if name:
        parts.append(name)
    if form_type:
        parts.append(form_type)
    if archived is not None:
        parts.append(f"archived {archived}")
    if published is not None:
        parts.append(f"published {published}")
    if labels:
        parts.append("fields " + ", ".join(labels))
    if submit_actions:
        parts.append("submit actions " + "; ".join(submit_actions))
    if portal_id is not None:
        parts.append(f"portal {portal_id}")
    return "; ".join(parts)


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return default


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
