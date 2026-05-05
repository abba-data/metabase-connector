# mrr_trend

> v1.0.0 · scope `general` · freshness 60d

Monthly MRR series with customer-type and partner-type breakdowns. Backed by Metabase #159 methodology.

**Source Metabase card:** `159`

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `months_back` | `integer` | no | default `24` |
| `partner_subtype` | `string` | no |  |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `series` | `list[object]` | yes |  |

## Response envelope

Every response wraps the data above:

```json
{
  "data": { ... },
  "meta": {
    "freshness_window_days": 60,
    "source_question_id": 159,
    "kind": "catalog",
    "request_id": "..."
  }
}
```

## Example

```bash
curl -X POST $CONNECTOR_URL/rpc/mrr_trend \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
