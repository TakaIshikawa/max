"""Tact API client — push specs to tact daemon via REST."""

from __future__ import annotations

import httpx

from max.types.tact_spec import TactSpec

DEFAULT_TACT_URL = "http://localhost:4800/api/v1"


async def push_to_tact(
    spec: TactSpec,
    *,
    tact_url: str = DEFAULT_TACT_URL,
) -> dict[str, bool]:
    """Push a TactSpec to the tact daemon via REST API.

    Returns a dict indicating success/failure for each endpoint.
    """
    results: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # PUT /product
        try:
            resp = await client.put(
                f"{tact_url}/product",
                json=spec.product.model_dump(by_alias=True),
            )
            resp.raise_for_status()
            results["product"] = True
        except Exception:
            results["product"] = False

        # PUT /architecture
        try:
            resp = await client.put(
                f"{tact_url}/architecture",
                json=spec.architecture.model_dump(by_alias=True),
            )
            resp.raise_for_status()
            results["architecture"] = True
        except Exception:
            results["architecture"] = False

        # POST /requirements (one per requirement)
        req_success = 0
        req_total = len(spec.requirements)
        for req in spec.requirements:
            try:
                resp = await client.post(
                    f"{tact_url}/requirements",
                    json=req.model_dump(by_alias=True),
                )
                resp.raise_for_status()
                req_success += 1
            except Exception:
                pass
        results["requirements"] = req_success == req_total
        results["requirements_count"] = req_success

    return results


def push_to_tact_sync(
    spec: TactSpec,
    *,
    tact_url: str = DEFAULT_TACT_URL,
) -> dict[str, bool]:
    """Synchronous wrapper for push_to_tact."""
    import asyncio
    return asyncio.run(push_to_tact(spec, tact_url=tact_url))
