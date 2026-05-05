# channel_split

> v1.0.0 · scope `general` · freshness 60d

Partner vs direct net-revenue split with line counts and distinct license counts. Channel = partnerName IS NOT NULL.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `start_date` | `string` | yes |  |
| `end_date` | `string` | yes |  |
| `license_types` | `list[{'COMMERCIAL', 'ACADEMIC'}]` | no |  |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `partner` | `object` | yes |  |
| `direct` | `object` | yes |  |
| `total` | `object` | yes |  |

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
curl -X POST $CONNECTOR_URL/rpc/channel_split \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
