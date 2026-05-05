# read_audit

> v1.0.0 · scope `operator` · freshness 0d

Operator-only audit-log read with filters. Returns the structured audit records SEC-02 writes.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `start_time` | `string` | no |  |
| `end_time` | `string` | no |  |
| `caller_id` | `string` | no |  |
| `rpc_name` | `string` | no |  |
| `kind` | `{'catalog', 'raw'}` | no |  |
| `status` | `{'success', 'error'}` | no |  |
| `limit` | `integer` | no | default `100` |
| `offset` | `integer` | no | default `0` |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `records` | `list[object]` | yes |  |
| `next_offset` | `integer` | no |  |
| `queried_at` | `string` | yes |  |

## Response envelope

Every response wraps the data above:

```json
{
  "data": { ... },
  "meta": {
    "freshness_window_days": 0,
    "source_question_id": null,
    "kind": "catalog",
    "request_id": "..."
  }
}
```

## Example

```bash
curl -X POST $CONNECTOR_URL/rpc/read_audit \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
