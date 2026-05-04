from __future__ import annotations

from typing import Any


def metabase_rows_as_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Reshape a Metabase dataset_query payload into row-dicts keyed by column name.

    Metabase returns: {"data": {"rows": [[...], ...], "cols": [{"name": "..."}, ...], ...}, ...}.
    """
    data = payload.get("data") or {}
    rows = data.get("rows") or []
    cols = data.get("cols") or []
    names = [c.get("name") for c in cols]
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({names[i]: row[i] for i in range(min(len(names), len(row)))})
    return out
