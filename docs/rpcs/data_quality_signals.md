# data_quality_signals

> v1.0.0 · scope `general` · freshness 60d

Per-check data-quality signals (OK/WATCH/ACTION) with supporting count or sample. Same view for consumers and operators.

## Input

_(none)_

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `checks` | `list[object]` | yes |  |

## Response envelope

Every response wraps the data above:

```json
{
  "data": { ... },
  "meta": {
    "freshness_window_days": 60,
    "source_question_id": null,
    "kind": "catalog",
    "request_id": "..."
  }
}
```

## Example

```bash
curl -X POST $CONNECTOR_URL/rpc/data_quality_signals \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
