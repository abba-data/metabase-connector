# top_partners

> v1.0.0 · scope `general` · freshness 60d

Ranked partner list by net revenue over the date window.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `start_date` | `string` | yes |  |
| `end_date` | `string` | yes |  |
| `limit` | `integer` | no | default `10` |
| `consolidate` | `boolean` | no | default `True` |

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
curl -X POST $CONNECTOR_URL/rpc/top_partners \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
