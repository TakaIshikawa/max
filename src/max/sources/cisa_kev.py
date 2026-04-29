"""CISA Known Exploited Vulnerabilities catalog source adapter."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CISA_KEV_FEED_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
CISA_KEV_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"

_DEFAULT_MAX_AGE_DAYS = 365


class CisaKevAdapter(SourceAdapter):
    """Fetch CISA KEV catalog entries as high-urgency vulnerability signals."""

    config_keys = [
        "keywords",
        "vendors",
        "products",
        "max_age_days",
        "known_ransomware_campaign_use",
        "catalog_url",
    ]
    required_keys: list[str] = []
    description = (
        "Fetches CISA Known Exploited Vulnerabilities catalog entries with filters "
        "for vendor, product, age, keywords, and known ransomware campaign use."
    )

    @property
    def name(self) -> str:
        return "cisa_kev"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", [])

    @property
    def vendors(self) -> list[str]:
        return _string_list(self._config.get("vendors"))

    @property
    def products(self) -> list[str]:
        return _string_list(self._config.get("products"))

    @property
    def max_age_days(self) -> int:
        value = self._config.get("max_age_days", _DEFAULT_MAX_AGE_DAYS)
        if isinstance(value, bool):
            return _DEFAULT_MAX_AGE_DAYS
        try:
            return int(value)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_AGE_DAYS

    @property
    def known_ransomware_campaign_use(self) -> bool | None:
        if "known_ransomware_campaign_use" not in self._config:
            return None
        return _parse_optional_bool(self._config.get("known_ransomware_campaign_use"))

    @property
    def catalog_url(self) -> str:
        return str(self._config.get("catalog_url", CISA_KEV_FEED_URL))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await fetch_with_retry(
                    self.catalog_url,
                    client,
                    adapter_name=self.name,
                    headers={"Accept": "application/json"},
                )
                payload = response.json()
        except AdapterFetchError:
            logger.warning("%s: failed to fetch CISA KEV catalog", self.name, exc_info=True)
            return []
        except (httpx.RequestError, httpx.TimeoutException):
            logger.warning("%s: failed to fetch CISA KEV catalog", self.name, exc_info=True)
            return []
        except ValueError as exc:
            raise SourceParseError(
                "Malformed CISA KEV catalog JSON",
                adapter_name=self.name,
            ) from exc

        return parse_cisa_kev_catalog(
            payload,
            adapter_name=self.name,
            keywords=self.keywords,
            vendors=self.vendors,
            products=self.products,
            max_age_days=self.max_age_days,
            known_ransomware_campaign_use=self.known_ransomware_campaign_use,
            limit=limit,
        )


def parse_cisa_kev_catalog(
    payload: Any,
    *,
    adapter_name: str = "cisa_kev",
    keywords: list[str] | None = None,
    vendors: list[str] | None = None,
    products: list[str] | None = None,
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    known_ransomware_campaign_use: bool | None = None,
    limit: int = 30,
    now: datetime | None = None,
) -> list[Signal]:
    """Parse a CISA KEV JSON payload into deterministic security signals."""
    if not isinstance(payload, dict):
        raise SourceParseError(
            "Malformed CISA KEV catalog: expected JSON object",
            adapter_name=adapter_name,
        )

    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise SourceParseError(
            "Malformed CISA KEV catalog: vulnerabilities must be a list",
            adapter_name=adapter_name,
        )

    cutoff = _age_cutoff(max_age_days, now=now)
    signals: list[Signal] = []
    seen_cves: set[str] = set()

    for item in vulnerabilities:
        if len(signals) >= limit:
            break
        if not isinstance(item, dict):
            continue

        signal = _signal_from_entry(
            item,
            adapter_name=adapter_name,
            cutoff=cutoff,
            keywords=keywords or [],
            vendors=vendors or [],
            products=products or [],
            known_ransomware_campaign_use=known_ransomware_campaign_use,
        )
        if signal is None:
            continue

        cve_id = signal.metadata["cve_id"]
        if cve_id in seen_cves:
            continue
        seen_cves.add(cve_id)
        signals.append(signal)

    return signals


def _signal_from_entry(
    entry: dict[str, Any],
    *,
    adapter_name: str,
    cutoff: datetime | None,
    keywords: list[str],
    vendors: list[str],
    products: list[str],
    known_ransomware_campaign_use: bool | None,
) -> Signal | None:
    cve_id = _clean(entry.get("cveID"))
    if not cve_id:
        return None

    vendor = _clean(entry.get("vendorProject"))
    product = _clean(entry.get("product"))
    vulnerability_name = _clean(entry.get("vulnerabilityName"))
    short_description = _clean(entry.get("shortDescription"))
    required_action = _clean(entry.get("requiredAction"))
    ransomware_use = _clean(entry.get("knownRansomwareCampaignUse"))
    notes = _clean(entry.get("notes"))
    date_added = _parse_date(entry.get("dateAdded"))
    due_date = _parse_date(entry.get("dueDate"))

    if cutoff is not None and (date_added is None or date_added < cutoff):
        return None
    if vendors and not _matches_any(vendor, vendors):
        return None
    if products and not _matches_any(product, products):
        return None
    if keywords and not _matches_any(_entry_search_text(entry), keywords):
        return None
    if known_ransomware_campaign_use is not None:
        is_known = ransomware_use.strip().lower() == "known"
        if is_known != known_ransomware_campaign_use:
            return None

    content_parts = [
        short_description,
        f"Required action: {required_action}" if required_action else "",
        f"Due date: {due_date.date().isoformat()}" if due_date else "",
        f"Known ransomware campaign use: {ransomware_use}" if ransomware_use else "",
        notes,
    ]
    content = " ".join(part for part in content_parts if part)[:700]
    title_subject = vulnerability_name or f"{vendor} {product}".strip() or cve_id

    return Signal(
        id=f"{adapter_name}:{cve_id}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"CISA KEV {cve_id}: {title_subject}"[:240],
        content=content or title_subject,
        url=_kev_entry_url(cve_id),
        published_at=date_added,
        tags=_build_tags(cve_id, vendor, product, ransomware_use),
        credibility=0.95,
        metadata={
            "cve_id": cve_id,
            "vendor_project": vendor,
            "product": product,
            "vulnerability_name": vulnerability_name,
            "date_added": date_added.date().isoformat() if date_added else "",
            "due_date": due_date.date().isoformat() if due_date else "",
            "known_ransomware_campaign_use": ransomware_use,
            "required_action": required_action,
            "notes": notes,
            "source_catalog": "cisa_kev",
            "signal_role": "problem",
        },
    )


def _age_cutoff(max_age_days: int, *, now: datetime | None = None) -> datetime | None:
    if max_age_days <= 0:
        return None
    reference = now or datetime.now(timezone.utc)
    return reference.astimezone(timezone.utc) - timedelta(days=max_age_days)


def _entry_search_text(entry: dict[str, Any]) -> str:
    values = [
        entry.get("cveID"),
        entry.get("vendorProject"),
        entry.get("product"),
        entry.get("vulnerabilityName"),
        entry.get("shortDescription"),
        entry.get("requiredAction"),
        entry.get("notes"),
    ]
    return " ".join(str(value) for value in values if value is not None)


def _matches_any(value: str, terms: list[str]) -> bool:
    value_lower = value.lower()
    return any(term.lower() in value_lower for term in terms if term)


def _build_tags(cve_id: str, vendor: str, product: str, ransomware_use: str) -> list[str]:
    tags = {"security", "cve", "cisa-kev", "known-exploited", cve_id.lower()}
    if ransomware_use.strip().lower() == "known":
        tags.add("ransomware")
    for value in (vendor, product):
        slug = _slug(value)
        if slug:
            tags.add(slug)
    return sorted(tags)[:10]


def _kev_entry_url(cve_id: str) -> str:
    return f"{CISA_KEV_CATALOG_URL}?search_api_fulltext={quote_plus(cve_id)}"


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"known", "true", "yes", "1"}:
            return True
        if normalized in {"unknown", "false", "no", "0"}:
            return False
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _slug(value: str) -> str:
    return "-".join(value.lower().replace("/", " ").split())[:48]
