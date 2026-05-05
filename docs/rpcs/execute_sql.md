# execute_sql

> v1.0.0 · scope `raw_sql` · freshness 60d

Raw-SQL escape hatch. Forwards native SQL to Metabase POST /api/dataset. No connector-side sanitisation; gated by 'raw_sql' scope. Response envelope kind='raw'.

## Input

| Field | Type | Required | Description |
|---|---|---|---|
| `database_id` | `integer` | yes | Metabase database id (see GET /api/database). |
| `sql` | `string` | yes | Native SQL to execute against the database. |
| `parameters` | `list[object]` | no | Metabase parameter list, e.g. [{'type':'text','target':[...],'value':'...'}]. |
| `template_tags` | `object` | no | Optional native template-tag declarations keyed by tag name. |

## Output (`data` field)

| Field | Type | Required | Description |
|---|---|---|---|
| `columns` | `list[object]` | yes |  |
| `rows` | `list[list[any]]` | yes |  |
| `row_count` | `integer` | yes |  |
| `running_time_ms` | `integer` | no |  |
| `status` | `string` | no |  |
| `rows_truncated` | `integer` | no |  |
| `executed_at` | `string` | yes |  |

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
curl -X POST $CONNECTOR_URL/rpc/execute_sql \
  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```
