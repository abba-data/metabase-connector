# describe_catalog

> v1.0.0 · scope `general` · freshness 0d

List all catalog RPCs with input/output JSON Schema, version, scope, and freshness.

## Input

_(none)_

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `rpcs` | `list[object]` | yes |  |
| `generated_at` | `string` | yes |  |

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
curl -X POST $CONNECTOR_URL/rpc/describe_catalog \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
