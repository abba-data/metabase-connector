# partner_revenue

> v1.0.0 · scope `general` · freshness 60d

Net revenue per partner over the date window. Applies canonical partner scope, license-type filter, and vendorAmount sign convention.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `start_date` | `string` | yes |  |
| `end_date` | `string` | yes |  |
| `consolidate` | `boolean` | no | default `True` |
| `license_types` | `list[{'COMMERCIAL', 'ACADEMIC'}]` | no |  |

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
curl -X POST $CONNECTOR_URL/rpc/partner_revenue \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
