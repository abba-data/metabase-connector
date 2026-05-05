# revenue_comparison

> v1.0.0 · scope `general` · freshness 60d

Period-over-period net-revenue comparison split by channel / sale_type / partner.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `period_a` | `object | string` | yes |  |
| `period_b` | `object | string` | yes |  |
| `dimension` | `{'channel', 'sale_type', 'partner'}` | no |  |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `period_a` | `object` | yes |  |
| `period_b` | `object` | yes |  |
| `deltas` | `list[object]` | yes |  |

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
curl -X POST $CONNECTOR_URL/rpc/revenue_comparison \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
