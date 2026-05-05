"""Interactive-script sample.

Calls describe_catalog to discover available RPCs, then runs a few queries
and prints summary tables. Useful from a terminal or notebook for quick
ad-hoc exploration.

Usage:
  CONNECTOR_URL=http://localhost:8000 \\
  CONNECTOR_API_KEY=<your-key> \\
  python explore.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from typing import Any

import httpx


def call(client: httpx.Client, rpc: str, body: dict[str, Any]) -> dict[str, Any]:
    r = client.post(f"/rpc/{rpc}", json=body)
    if r.status_code >= 400:
        raise SystemExit(f"{rpc} -> {r.status_code}: {r.text}")
    return r.json()


def main() -> int:
    base = os.environ.get("CONNECTOR_URL", "http://localhost:8000").rstrip("/")
    api_key = os.environ.get("CONNECTOR_API_KEY")
    if not api_key:
        print("CONNECTOR_API_KEY not set", file=sys.stderr)
        return 2

    with httpx.Client(
        base_url=base,
        headers={"X-Connector-API-Key": api_key},
        timeout=60.0,
    ) as client:
        catalog = call(client, "describe_catalog", {})
        print("=== Catalog ===")
        for entry in catalog["data"]["rpcs"]:
            print(f"  {entry['name']:24s}  v{entry['version']}  scope={entry['required_scope']}")
        print(f"  request_id={catalog['meta']['request_id']}\n")

        end = date.today()
        start = end - timedelta(days=90)
        split = call(
            client,
            "channel_split",
            {"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
        print(f"=== channel_split {start} → {end} ===")
        d = split["data"]
        print(f"  partner: revenue={d['partner']['revenue']}  lines={d['partner']['line_count']}")
        print(f"  direct:  revenue={d['direct']['revenue']}   lines={d['direct']['line_count']}")
        print(f"  total:   revenue={d['total']['revenue']}    lines={d['total']['line_count']}\n")

        risk = call(client, "arr_at_risk", {"horizon_days": 60, "group_by": "overall"})
        print("=== arr_at_risk (60d horizon, overall) ===")
        rd = risk["data"]
        print(f"  total_arr_at_risk={rd['total_arr_at_risk']}  buckets={len(rd['breakdown'])}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
