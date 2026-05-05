# upsell_opportunities

> v1.0.0 · scope `general` · freshness 60d

Tier-grown licenses approaching renewal with projected re-priced ARR. Projection arithmetic lives in saved-question SQL.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `horizon_days` | `integer` | no | default `60` |
| `min_seat_delta` | `integer` | no | default `1` |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `rows` | `list[object]` | yes |  |

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
curl -X POST $CONNECTOR_URL/rpc/upsell_opportunities \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
