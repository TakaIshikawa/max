"""ClinicalTrials.gov source adapter."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CLINICAL_TRIALS_STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"
CLINICAL_TRIALS_STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"

_DEFAULT_TERMS = [
    "clinical workflow artificial intelligence",
    "clinical decision support",
    "EHR workflow automation",
    "remote patient monitoring",
    "digital health care coordination",
]


class ClinicalTrialsAdapter(SourceAdapter):
    """Fetch ClinicalTrials.gov study records as healthcare validation signals."""

    @property
    def name(self) -> str:
        return "clinical_trials"

    @property
    def source_type(self) -> str:
        return SignalSourceType.EXPERIMENT.value

    @property
    def terms(self) -> list[str]:
        return self._configured_terms("terms", _DEFAULT_TERMS)

    @property
    def conditions(self) -> list[str]:
        return self._configured_terms("conditions", [])

    @property
    def intervention_terms(self) -> list[str]:
        configured = self._config.get("intervention_terms", self._config.get("interventions"))
        if configured is None:
            values = []
        elif isinstance(configured, str):
            values = [configured]
        else:
            values = list(configured)
        return _dedupe_configured_terms(values, self._config.get("watchlist_terms", []))

    @property
    def max_results_per_query(self) -> int:
        try:
            return max(int(self._config.get("max_results_per_query", 25)), 1)
        except (TypeError, ValueError):
            return 25

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_nct_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for params, query_label in self._query_params(limit):
                if len(signals) >= limit:
                    break

                page_token: str | None = None
                while len(signals) < limit:
                    request_params = {
                        **params,
                        "pageSize": min(self.max_results_per_query, max(limit - len(signals), 1)),
                        "format": "json",
                    }
                    if page_token:
                        request_params["pageToken"] = page_token

                    data = await self._fetch_page(client, request_params, query_label)
                    if not data:
                        break

                    for study in _studies(data):
                        if len(signals) >= limit:
                            break
                        signal = _study_to_signal(study, adapter_name=self.name, search_query=query_label)
                        if signal is None:
                            continue
                        nct_id = signal.metadata["nct_id"]
                        if nct_id in seen_nct_ids:
                            continue
                        seen_nct_ids.add(nct_id)
                        signals.append(signal)

                    page_token = _string_or_none(data.get("nextPageToken"))
                    if not page_token:
                        break

        return signals[:limit]

    def _query_params(self, limit: int) -> list[tuple[dict[str, str], str]]:
        del limit
        queries: list[tuple[dict[str, str], str]] = []
        for condition in self.conditions:
            queries.append(({"query.cond": condition}, condition))
        for intervention in self.intervention_terms:
            queries.append(({"query.intr": intervention}, intervention))
        for term in self.terms:
            queries.append(({"query.term": term}, term))
        return queries

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        params: dict[str, Any],
        query_label: str,
    ) -> dict[str, Any] | None:
        try:
            response = await fetch_with_retry(
                CLINICAL_TRIALS_STUDIES_URL,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-clinical-trials-adapter/0.1"},
            )
            data = response.json()
            return data if isinstance(data, dict) else None
        except AdapterFetchError as exc:
            logger.warning(
                "%s: failed to fetch ClinicalTrials.gov studies for '%s': %s",
                self.name,
                query_label,
                exc,
            )
        except ValueError as exc:
            logger.warning(
                "%s: failed to parse ClinicalTrials.gov response for '%s': %s",
                self.name,
                query_label,
                exc,
            )
        return None


def _study_to_signal(
    study: dict[str, Any],
    *,
    adapter_name: str,
    search_query: str,
) -> Signal | None:
    protocol = _dict(study.get("protocolSection"))
    identification = _dict(protocol.get("identificationModule"))
    nct_id = _string_or_none(identification.get("nctId"))
    if nct_id is None:
        return None

    status_module = _dict(protocol.get("statusModule"))
    conditions_module = _dict(protocol.get("conditionsModule"))
    interventions_module = _dict(protocol.get("armsInterventionsModule"))
    sponsor_module = _dict(protocol.get("sponsorCollaboratorsModule"))
    design_module = _dict(protocol.get("designModule"))
    locations_module = _dict(protocol.get("contactsLocationsModule"))
    description_module = _dict(protocol.get("descriptionModule"))

    title = (
        _string_or_none(identification.get("briefTitle"))
        or _string_or_none(identification.get("officialTitle"))
        or nct_id
    )
    summary = _string_or_none(description_module.get("briefSummary")) or title
    status = _string_or_none(status_module.get("overallStatus"))
    phases = _string_list(design_module.get("phases"))
    conditions = _string_list(conditions_module.get("conditions"))
    interventions = _intervention_names(interventions_module.get("interventions"))
    sponsor = _string_or_none(_dict(sponsor_module.get("leadSponsor")).get("name"))
    enrollment_count = _int_or_none(_dict(design_module.get("enrollmentInfo")).get("count"))
    start_date = _date_string(_dict(status_module.get("startDateStruct")).get("date"))
    completion_date = _date_string(_dict(status_module.get("completionDateStruct")).get("date"))
    locations_count = len(_list_of_dicts(locations_module.get("locations")))
    source_url = CLINICAL_TRIALS_STUDY_URL.format(nct_id=nct_id)

    content_parts = [summary]
    if status:
        content_parts.append(f"Status: {status}")
    if conditions:
        content_parts.append(f"Conditions: {', '.join(conditions[:5])}")
    if interventions:
        content_parts.append(f"Interventions: {', '.join(interventions[:5])}")

    return Signal(
        id=f"{adapter_name}:{nct_id}",
        source_type=SignalSourceType.EXPERIMENT,
        source_adapter=adapter_name,
        title=title[:240],
        content="\n".join(content_parts)[:1000],
        url=source_url,
        published_at=_parse_date(start_date),
        tags=_build_tags(conditions, interventions, phases, status),
        credibility=_credibility(status, enrollment_count, sponsor),
        metadata={
            "nct_id": nct_id,
            "status": status,
            "phases": phases,
            "conditions": conditions,
            "interventions": interventions,
            "sponsor": sponsor,
            "enrollment_count": enrollment_count,
            "start_date": start_date,
            "completion_date": completion_date,
            "locations_count": locations_count,
            "source_url": source_url,
            "search_query": search_query,
            "signal_role": "market",
        },
    )


def _studies(data: dict[str, Any]) -> list[dict[str, Any]]:
    return _list_of_dicts(data.get("studies"))


def _intervention_names(value: Any) -> list[str]:
    names: list[str] = []
    for intervention in _list_of_dicts(value):
        name = _string_or_none(intervention.get("name"))
        if name:
            names.append(name)
    return _dedupe(names)


def _build_tags(
    conditions: list[str],
    interventions: list[str],
    phases: list[str],
    status: str | None,
) -> list[str]:
    tags = ["clinical-trials"]
    tags.extend(_slug(value) for value in conditions[:4])
    tags.extend(_slug(value) for value in interventions[:3])
    tags.extend(_slug(value) for value in phases[:2])
    if status:
        tags.append(_slug(status))
    return _dedupe([tag for tag in tags if tag])[:10]


def _credibility(status: str | None, enrollment_count: int | None, sponsor: str | None) -> float:
    score = 0.55
    normalized_status = (status or "").lower()
    if "recruit" in normalized_status or "active" in normalized_status:
        score += 0.1
    if "completed" in normalized_status:
        score += 0.15
    if enrollment_count:
        score += min(enrollment_count / 5000, 0.15)
    if sponsor:
        score += 0.05
    return min(score, 0.9)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _date_string(value: Any) -> str | None:
    return _string_or_none(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([item.strip() for item in value if isinstance(item, str) and item.strip()])


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _slug(value: str) -> str:
    return "-".join(value.lower().replace("_", " ").split())


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _dedupe_configured_terms(values: list[Any], watchlist_terms: Any) -> list[str]:
    watchlist = watchlist_terms if isinstance(watchlist_terms, list) else []
    terms: list[str] = []
    for value in [*values, *watchlist]:
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    return _dedupe(terms)
