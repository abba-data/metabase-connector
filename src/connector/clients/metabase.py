from __future__ import annotations

import logging
from typing import Any

import httpx

from connector.errors import (
    ExceededSyncWindowError,
    MetabaseError,
    MetabaseTimeoutError,
    MetabaseUnavailableError,
)

log = logging.getLogger("connector.metabase")


class MetabaseClient:
    """Thin wrapper around the subset of the Metabase HTTP API we need.

    Per spec CRT-02A:
    - `execute_card(card_id, params, timeout)` runs a saved question.
    - `execute_dataset(sql, db_id, timeout)` runs raw SQL (escape hatch).
    - Auth is `X-API-Key` (Metabase service-account key).
    - 202 responses surface as EXCEEDED_SYNC_WINDOW.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        version_pin: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._version_pin = version_pin or None
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(self._timeout),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            r = await self._client.get("/api/health")
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException as e:
            raise MetabaseTimeoutError("Metabase health check timed out.") from e
        except httpx.HTTPError as e:
            raise MetabaseUnavailableError(f"Metabase health check failed: {e}") from e

    async def session_properties(self) -> dict[str, Any]:
        r = await self._client.get("/api/session/properties")
        r.raise_for_status()
        return r.json()

    async def assert_version(self) -> None:
        if not self._version_pin:
            return
        props = await self.session_properties()
        version = (props.get("version") or {}).get("tag") or props.get("version")
        if version != self._version_pin:
            raise MetabaseUnavailableError(
                f"Metabase version mismatch. Pinned={self._version_pin!r} actual={version!r}.",
            )

    async def execute_card(
        self,
        card_id: int,
        *,
        parameters: list[dict[str, Any]] | None = None,
        ignore_cache: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"ignore_cache": ignore_cache}
        if parameters:
            body["parameters"] = parameters
        return await self._post_query(f"/api/card/{card_id}/query", body=body, timeout=timeout)

    async def execute_dataset(
        self,
        *,
        database_id: int,
        sql: str,
        parameters: list[dict[str, Any]] | None = None,
        template_tags: dict[str, dict[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        native: dict[str, Any] = {"query": sql}
        if template_tags:
            native["template-tags"] = template_tags
        body: dict[str, Any] = {
            "database": database_id,
            "type": "native",
            "native": native,
            "parameters": parameters or [],
        }
        return await self._post_query("/api/dataset", body=body, timeout=timeout)

    async def _post_query(
        self, path: str, *, body: dict[str, Any], timeout: float | None
    ) -> dict[str, Any]:
        request_timeout = httpx.Timeout(timeout if timeout is not None else self._timeout)
        try:
            r = await self._client.post(path, json=body, timeout=request_timeout)
        except httpx.TimeoutException as e:
            raise MetabaseTimeoutError(f"Metabase request to {path} timed out.") from e
        except httpx.HTTPError as e:
            raise MetabaseUnavailableError(f"Metabase request to {path} failed: {e}") from e

        if r.status_code >= 500:
            raise MetabaseUnavailableError(
                f"Metabase {r.status_code} on {path}: {_safe_text(r)}",
            )
        if r.status_code >= 400:
            raise MetabaseError(
                f"Metabase {r.status_code} on {path}: {_safe_text(r)}",
                status_code=502,
                debug={"upstream_status": r.status_code},
            )

        # Metabase quirk: /api/dataset and /api/card/{id}/query return HTTP 202
        # with the full result body when the query completed within the sync
        # window. Surface EXCEEDED_SYNC_WINDOW only if the body is missing the
        # completed-query payload.
        try:
            payload = r.json()
        except ValueError as e:
            raise MetabaseError(f"Metabase non-JSON response on {path}.") from e

        if r.status_code == 202 and not _looks_completed(payload):
            raise ExceededSyncWindowError(
                "Metabase returned 202 Accepted with no result body — query exceeded the synchronous window."
            )
        return payload


def _looks_completed(payload: Any) -> bool:
    """A Metabase dataset_query response is treated as complete when the
    body carries a `data.rows` array or an explicit `status: 'completed'`.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("status") == "completed":
        return True
    data = payload.get("data")
    return isinstance(data, dict) and isinstance(data.get("rows"), list)


def _safe_text(r: httpx.Response, limit: int = 500) -> str:
    text = r.text or ""
    return text[:limit]
