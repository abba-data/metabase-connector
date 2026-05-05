# license_query

> v1.0.0 · scope `general` · freshness 60d

Flexible license lookup with named optional filters. Active-license rule applied via WHF-01 view.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `partner` | `string` | no |  |
| `company` | `string` | no |  |
| `addon` | `string` | no |  |
| `status` | `{'active', 'inactive', 'cancelled'}` | no |  |
| `hosting` | `{'Cloud', 'DataCenter', 'Server'}` | no |  |
| `license_type` | `{'COMMERCIAL', 'ACADEMIC'}` | no |  |
| `limit` | `integer` | no | default `100` |

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
curl -X POST $CONNECTOR_URL/rpc/license_query \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
