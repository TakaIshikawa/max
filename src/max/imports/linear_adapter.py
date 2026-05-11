"""Linear issue import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearAdapter(SourceAdapter):
    """Fetch Linear issues and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str = LINEAR_GRAPHQL_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else os.getenv("LINEAR_API_KEY")
        self.api_url = api_url
        self._client = client

    @property
    def name(self) -> str:
        return "linear_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def team_keys(self) -> list[str]:
        return self._string_list("team_keys")

    @property
    def project_ids(self) -> list[str]:
        return self._string_list("project_ids")

    @property
    def states(self) -> list[str]:
        return self._string_list("states")

    @property
    def labels(self) -> list[str]:
        return self._string_list("labels")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            try:
                response = await client.post(
                    self.api_url,
                    json=self._graphql_payload(limit),
                    headers={
                        "Authorization": self.token,
                        "Content-Type": "application/json",
                        "User-Agent": "max-linear-import/1",
                    },
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Linear issue fetch failed", exc_info=True)
                return []
        finally:
            if close_client:
                await client.aclose()

        if body.get("errors"):
            logger.warning("Linear issue fetch returned GraphQL errors: %s", body.get("errors"))
            return []

        issues = (((body.get("data") or {}).get("issues") or {}).get("nodes") or [])
        signals: list[Signal] = []
        seen: set[str] = set()
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            signal = self._issue_to_signal(issue, seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    def _graphql_payload(self, limit: int) -> dict[str, Any]:
        return {
            "query": ISSUES_QUERY,
            "variables": {
                "first": min(limit, 100),
                "filter": self._issue_filter(),
            },
        }

    def _issue_filter(self) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if self.team_keys:
            filters.append({"team": {"key": {"in": self.team_keys}}})
        if self.project_ids:
            filters.append({"project": {"id": {"in": self.project_ids}}})
        if self.states:
            filters.append({"state": {"name": {"in": self.states}}})
        if self.labels:
            filters.append({"labels": {"name": {"in": self.labels}}})
        if not filters:
            return {}
        return {"and": filters}

    def _issue_to_signal(self, issue: dict[str, Any], seen: set[str]) -> Signal | None:
        issue_id = _text(issue.get("id"))
        if not issue_id or issue_id in seen:
            return None
        seen.add(issue_id)

        labels = [_text(label.get("name")) for label in ((issue.get("labels") or {}).get("nodes") or []) if isinstance(label, dict)]
        labels = [label for label in labels if label]
        state = issue.get("state") if isinstance(issue.get("state"), dict) else {}
        assignee = issue.get("assignee") if isinstance(issue.get("assignee"), dict) else {}
        team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
        project = issue.get("project") if isinstance(issue.get("project"), dict) else {}

        return Signal(
            source_type=SignalSourceType.ROADMAP,
            source_adapter=self.name,
            title=_text(issue.get("title")) or _text(issue.get("identifier")) or issue_id,
            content=_text(issue.get("description"))[:1000],
            url=_text(issue.get("url")),
            author=_text(assignee.get("name")) or _text(assignee.get("email")) or None,
            published_at=_parse_dt(issue.get("createdAt")),
            tags=sorted({"linear", *labels, _text(state.get("name"))} - {""})[:10],
            credibility=0.7,
            metadata={
                "linear_issue_id": issue_id,
                "identifier": issue.get("identifier"),
                "state": state.get("name"),
                "priority": issue.get("priority"),
                "priority_label": issue.get("priorityLabel"),
                "assignee": assignee.get("name"),
                "assignee_email": assignee.get("email"),
                "labels": labels,
                "team_key": team.get("key"),
                "team_name": team.get("name"),
                "project_id": project.get("id"),
                "project_name": project.get("name"),
                "created_at": issue.get("createdAt"),
                "updated_at": issue.get("updatedAt"),
            },
        )

    def _string_list(self, key: str) -> list[str]:
        value = self._config.get(key, [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]


ISSUES_QUERY = """
query MaxLinearIssues($first: Int!, $filter: IssueFilter) {
  issues(first: $first, filter: $filter, orderBy: updatedAt) {
    nodes {
      id
      identifier
      title
      description
      url
      priority
      priorityLabel
      createdAt
      updatedAt
      state { name }
      assignee { name email }
      team { key name }
      project { id name }
      labels { nodes { name } }
    }
  }
}
"""


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
