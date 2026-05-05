"""LLM-agent sample.

Wraps the connector's catalog as Anthropic-style `tool` definitions so an
LLM agent can call `describe_catalog` once and self-construct subsequent
queries. The connector is the deterministic surface; the agent supplies
intent and parameter values.

This file is illustrative. Drop into your agent loop wherever you build
the `tools=[...]` payload.

Usage outline:
    from samples.llm.tools import build_tools, call_rpc
    tools = build_tools()
    # ... pass `tools` to anthropic.messages.create(...)
    # When the model emits a tool_use, route to call_rpc(name, input).
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


def _client() -> httpx.Client:
    base = os.environ.get("CONNECTOR_URL", "http://localhost:8000").rstrip("/")
    api_key = os.environ["CONNECTOR_API_KEY"]
    return httpx.Client(
        base_url=base,
        headers={"X-Connector-API-Key": api_key, "Content-Type": "application/json"},
        timeout=60.0,
    )


def fetch_catalog() -> list[dict[str, Any]]:
    with _client() as c:
        r = c.post("/rpc/describe_catalog", json={})
        r.raise_for_status()
        return r.json()["data"]["rpcs"]


def build_tools() -> list[dict[str, Any]]:
    """Translate catalog descriptors to Anthropic tool definitions.

    Each catalog entry's `input_schema` is a JSON Schema, which is the shape
    Anthropic's tool API expects under `input_schema`.
    """
    tools: list[dict[str, Any]] = []
    for entry in fetch_catalog():
        # Skip operator-only RPCs — agents shouldn't drive audit reads.
        if entry["required_scope"] == "operator":
            continue
        tools.append(
            {
                "name": entry["name"],
                "description": entry["description"],
                "input_schema": entry["input_schema"],
            }
        )
    return tools


def call_rpc(name: str, input_: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool_use the model emitted. Returns the connector's full
    Response envelope so the agent can surface freshness + source_question_id."""
    with _client() as c:
        r = c.post(f"/rpc/{name}", json=input_)
        if r.status_code >= 400:
            return {"error": {"code": r.status_code, "body": r.text}}
        return r.json()


if __name__ == "__main__":
    print(json.dumps(build_tools(), indent=2)[:2000])
