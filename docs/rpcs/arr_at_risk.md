# arr_at_risk

> v1.0.0 · scope `general` · freshness 60d

Licenses whose maintenanceEndDate falls within horizon_days, broken down by overall/partner/app.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `horizon_days` | `integer` | no | default `60` |
| `group_by` | `{'overall', 'partner', 'app'}` | no |  |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `total_arr_at_risk` | `number | string` | yes |  |
| `breakdown` | `list[object]` | yes |  |

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
curl -X POST $CONNECTOR_URL/rpc/arr_at_risk \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
