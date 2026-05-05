"""Write the live OpenAPI document to docs/openapi.json.

Run after model changes so the committed snapshot stays in sync. The
`openapi-snapshot-current` CI job verifies the snapshot matches what the
runtime would emit; `openapi-diff` flags breaking changes against the
previously-merged snapshot.

Usage:
  python tools/dump_openapi.py [path]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    # Set deterministic env so generated doc doesn't depend on shell state.
    os.environ.setdefault("AUDIT_STORE", "memory")
    os.environ.setdefault("CONNECTOR_API_KEYS", "")

    from connector.app import create_app
    from connector.audit.store import InMemoryAuditStore

    app = create_app(audit_store=InMemoryAuditStore())
    doc = app.openapi()
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} ({len(json.dumps(doc))} bytes, {len(doc.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
