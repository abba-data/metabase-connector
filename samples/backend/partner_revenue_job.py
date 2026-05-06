"""Backend service-account sample.

Calls the connector's `partner_revenue` RPC for the trailing 30 days and
writes the result as JSON to stdout (or a file path passed as argv[1]).

Usage:
  CONNECTOR_URL=http://localhost:8000 \\
  CONNECTOR_API_KEY=<your-key> \\
  python partner_revenue_job.py [output.json]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import httpx


def main() -> int:
    base = os.environ.get("CONNECTOR_URL", "http://localhost:8000").rstrip("/")
    api_key = os.environ.get("CONNECTOR_API_KEY")
    if not api_key:
        print("CONNECTOR_API_KEY not set", file=sys.stderr)
        return 2

    end = date.today()
    start = end - timedelta(days=30)
    body = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "consolidate": True,
        "license_types": ["COMMERCIAL", "ACADEMIC"],
    }

    r = httpx.post(
        f"{base}/rpc/partner_revenue",
        headers={"X-Connector-API-Key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=60.0,
    )
    if r.status_code != 200:
        print(f"connector returned {r.status_code}: {r.text}", file=sys.stderr)
        return 1

    payload = r.json()
    out = json.dumps(payload, indent=2, default=str)

    if len(sys.argv) > 1:
        from pathlib import Path

        Path(sys.argv[1]).write_text(out)
        print(f"wrote {sys.argv[1]} ({payload['data']['rows'].__len__()} rows)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
