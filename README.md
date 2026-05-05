# metabase-connector

A typed HTTP service that sits in front of Metabase and serves a curated menu of analytical queries.

Consumers — Python scripts, scheduled jobs, HubSpot integrations, Slack bots, **or LLM agents like Claude** — call one HTTP endpoint and get a number back. The connector handles auth, scope, rate limiting, audit logging, and response shape so consumers never write SQL directly.

```
consumer → connector (this) → Metabase API → warehouse
```

## What's available

**Catalog RPCs (one HTTP route each, JSON in / JSON out):**

| RPC | Returns |
|---|---|
| `describe_catalog` | List of every available RPC with its input/output schema, scope, version |
| `partner_revenue` | Net revenue per partner over a date window |
| `channel_split` | Partner vs direct revenue split |
| `top_partners` | Ranked partner list by revenue |
| `mrr_trend` | Monthly MRR series with breakdowns |
| `arr_at_risk` | Licenses with maintenance ending in `horizon_days` |
| `upsell_opportunities` | Tier-grown licenses approaching renewal |
| `revenue_comparison` | Period-over-period revenue split |
| `data_quality_signals` | OK/WATCH/ACTION health checks |
| `license_query` | Flexible license lookup |
| `execute_sql` | **Raw SQL escape hatch** (scope: `raw_sql`) |
| `read_audit` | Read the audit log (scope: `operator`) |

Per-RPC details: see [docs/rpcs/](docs/rpcs/) and the live OpenAPI doc at `/openapi.json`.

---

## Quickstart

### 1. Install

```bash
git clone https://github.com/abba-data/metabase-connector.git
cd metabase-connector
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+.

### 2. Configure

Copy `.env.example` → `.env` and fill it in.

```bash
# Metabase
METABASE_URL=https://analytics.atlasauthority.com
METABASE_API_KEY=mb_xxxxxxxxxxxxxxxx        # see "Getting a Metabase API key" below

# Connector consumer keys — each line is `<key>=<id>|<consumer_type>|<scopes>`.
# Multiple consumers separated by `;` or newlines.
CONNECTOR_API_KEYS=dev-key=abba|interactive_script|general,raw_sql,operator

# Audit log
AUDIT_STORE=sqlite                          # or `memory` for ephemeral
AUDIT_DB_PATH=./data/audit.sqlite

# Card IDs — set the ones you have, leave the rest unset.
# Find a card ID in its Metabase URL: …/question/<id>-some-slug
CARD_ID_PARTNER_REVENUE=
CARD_ID_CHANNEL_SPLIT=
CARD_ID_TOP_PARTNERS=
CARD_ID_MRR_TREND=159
CARD_ID_ARR_AT_RISK=
CARD_ID_UPSELL_OPPORTUNITIES=
CARD_ID_REVENUE_COMPARISON=
CARD_ID_DATA_QUALITY_SIGNALS=
CARD_ID_LICENSE_QUERY=
```

**Consumer types** are one of: `backend_service_account`, `interactive_script`, `llm_agent`.
**Scopes** are: `general` (catalog RPCs), `raw_sql` (adds `execute_sql`), `operator` (adds `read_audit`).

### 3. Boot

```bash
uvicorn connector.app:app --reload
```

Connector listens on `http://localhost:8000`.

### 4. Verify

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/healthz/upstream         # checks Metabase reachability
```

You should see `"status": "ok"` from both.

---

## Calling the RPCs

Every catalog RPC is a `POST /rpc/<name>` with a JSON body and the `X-Connector-API-Key` header.

### Example: list available RPCs

```bash
curl -X POST http://localhost:8000/rpc/describe_catalog \
  -H "X-Connector-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:

```json
{
  "data": {
    "rpcs": [
      {
        "name": "partner_revenue",
        "version": "1.0.0",
        "description": "Net revenue per partner over the date window…",
        "required_scope": "general",
        "freshness_window_days": 60,
        "source_question_id": 1001,
        "input_schema": { "$ref": "…", "properties": { … } },
        "output_schema": { … }
      },
      …
    ]
  },
  "meta": {
    "freshness_window_days": 0,
    "source_question_id": null,
    "kind": "catalog",
    "request_id": "5dd044f8815245e5a0c04dad003be582"
  }
}
```

### Example: partner revenue

```bash
curl -X POST http://localhost:8000/rpc/partner_revenue \
  -H "X-Connector-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-01-01",
    "end_date": "2026-03-31",
    "consolidate": true,
    "license_types": ["COMMERCIAL", "ACADEMIC"]
  }'
```

### Example: raw SQL (scope `raw_sql`)

```bash
curl -X POST http://localhost:8000/rpc/execute_sql \
  -H "X-Connector-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "database_id": 2,
    "sql": "SELECT * FROM transactions LIMIT 50"
  }'
```

The response carries 63 columns of typed data plus the envelope. SQL is forwarded byte-for-byte to Metabase — see [Security](#security) for why.

---

## Connecting AI tools

The connector is designed so any LLM agent can self-discover what's available via `describe_catalog` and call the RPCs as typed tools.

### Claude (Anthropic SDK)

The connector exposes every RPC's JSON Schema directly via `describe_catalog`. Anthropic's tool API takes JSON Schema as `input_schema`, so the translation is zero-effort.

A working example lives at [`samples/llm/tools.py`](samples/llm/tools.py). The minimum viable agent:

```python
import os
import anthropic
from samples.llm.tools import build_tools, call_rpc

client = anthropic.Anthropic()
tools = build_tools()  # fetches /rpc/describe_catalog and translates

messages = [
    {"role": "user", "content": "What was our partner channel revenue in Q1 2026?"}
]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=tools,
        messages=messages,
    )

    if response.stop_reason != "tool_use":
        # Final answer.
        for block in response.content:
            if block.type == "text":
                print(block.text)
        break

    # Route every tool_use to the connector.
    messages.append({"role": "assistant", "content": response.content})
    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            result = call_rpc(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })
    messages.append({"role": "user", "content": tool_results})
```

Run:

```bash
export CONNECTOR_URL=http://localhost:8000
export CONNECTOR_API_KEY=dev-key
export ANTHROPIC_API_KEY=sk-ant-...
python your_agent.py
```

Operator-scope RPCs (`read_audit`) are filtered out of `build_tools()` so the agent cannot drive audit reads — keep that key separate.

### Claude Code (CLI / IDE)

The connector exposes a standard HTTP interface, so any tool that supports tool use against an HTTP service can drive it. For Claude Code, point it at the connector via a custom MCP server (community packages exist, or write a thin wrapper that proxies to the connector's `describe_catalog` and per-RPC routes).

### Other AI tools

The OpenAPI document at `GET /openapi.json` is the canonical contract — any of these work:

- **OpenAI Assistants / Function Calling**: `describe_catalog`'s `input_schema` is JSON Schema; pass it as the `parameters` field of a function definition.
- **LangChain / LlamaIndex**: use `OpenAPISpec.from_url("http://localhost:8000/openapi.json")` then bind it to the agent's tool list.
- **Generic codegen**: `openapi-python-client generate --url http://localhost:8000/openapi.json` produces a typed client.

The point is that the connector's contract is fully described by the OpenAPI doc plus `describe_catalog` — there's nothing tool-specific in the connector itself.

---

## Response envelope

Every successful response is shaped `{ data, meta }`:

```json
{
  "data": { …RPC-specific payload… },
  "meta": {
    "freshness_window_days": 60,
    "source_question_id": 1001,
    "kind": "catalog",
    "request_id": "…"
  }
}
```

- `freshness_window_days` — Atlassian's eventual-consistency window. Recent data within this many days may shift on re-run; surface this caveat to humans.
- `source_question_id` — the Metabase saved-question id that produced the data, or `null` for raw SQL. Lets you trace any number back to a single SQL definition.
- `kind` — `catalog` for typed RPCs, `raw` for `execute_sql`.
- `request_id` — same id is in the audit log and the `X-Request-ID` response header. Grep this if a result looks off.

## Errors

All error responses share one shape:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request failed validation.",
  "request_id": "…",
  "debug": { "errors": [ … ] }
}
```

| Code | When |
|---|---|
| `UNAUTHORIZED` | Missing or invalid `X-Connector-API-Key` |
| `FORBIDDEN` | Caller's scope doesn't include the RPC's required scope |
| `VALIDATION_ERROR` | Pydantic input validation failed |
| `NOT_FOUND` | Unknown route |
| `RATE_LIMITED` | Per-consumer bucket exhausted; carries `Retry-After` header |
| `METABASE_TIMEOUT` | Metabase didn't respond inside the configured window |
| `METABASE_UNAVAILABLE` | Circuit breaker open or 5xx from Metabase |
| `METABASE_ERROR` | Metabase returned a 4xx (e.g. SQL syntax error) |
| `EXCEEDED_SYNC_WINDOW` | Metabase returned 202 with no payload (queued) |

The HTTP status code matches conventional REST: 401, 403, 422, 429, 5xx etc.

---

## Audit log

Every RPC call (success or failure, authenticated or not) writes a row to the audit log. Default storage is SQLite at `./data/audit.sqlite`; swap to Postgres or DataDog by implementing the `AuditStore` protocol.

Read it via the `read_audit` RPC (requires `operator` scope):

```bash
curl -X POST http://localhost:8000/rpc/read_audit \
  -H "X-Connector-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"limit": 50, "rpc_name": "execute_sql", "status": "error"}'
```

Each record carries: timestamp, request_id, caller_id, consumer_type, scope, rpc_name, rpc_version, parameters (with `password`/`secret`/`token`/`api_key` keys redacted), kind, source_question_id, latency_ms, status, error_code, connector_version.

## Telemetry

Prometheus metrics at `GET /metrics`:

- `connector_rpc_requests_total{rpc, consumer_type, status}` — call counter
- `connector_rpc_latency_seconds_bucket{rpc, consumer_type, le}` — latency histogram
- `connector_audit_writes_total{status}`
- `connector_circuit_breaker_state` — 0=closed, 1=open, 2=half-open

Cardinality is capped (no `caller_id` dimension — that's what the audit log is for).

---

## Security

### Two layers of auth

1. **Consumer → connector**: `X-Connector-API-Key` header, mapped to a `ConsumerIdentity` (id, consumer_type, scope set).
2. **Connector → Metabase**: a single Metabase service-account API key; the connector authenticates as this account for every upstream call.

### Three scopes

- `general` — all catalog RPCs.
- `raw_sql` — adds `execute_sql`. The SQL is forwarded byte-for-byte to Metabase; **the connector does no SQL sanitisation**. The Metabase service account's permissions are the actual security boundary — scope it at the Metabase level to only the databases and tables you want exposed.
- `operator` — adds `read_audit`.

### Getting a Metabase API key

In Metabase: **Admin → Settings → API keys → Create API key** → assign to a service-account user. Copy the generated `mb_…` key into `METABASE_API_KEY`.

For production you should also follow [SEC-03A in the spec](specs/data-connector-tech-spec.md): create a dedicated service-account user, a dedicated collection holding only the v1 saved questions, and configure permissions so the collection is execute-readable only by the service account. That way even a leaked connector identity can only execute the questions you've blessed.

---

## Project layout

```
src/connector/
  app.py                  # FastAPI app + middleware wiring
  settings.py             # env-loaded config
  errors.py               # typed error envelope + handlers
  registry.py             # RpcDescriptor + registry
  rpc_config.py           # CARD_ID_* env loaders
  audit/                  # SEC-02: AuditRecord, AuditStore (SQLite + memory)
  clients/metabase.py     # CRT-02: Metabase HTTP client
  middleware/             # request-id, audit, telemetry
  models/                 # Response[T], ResponseMeta, ConsumerType, Scope
  rpcs/                   # one file per RPC handler
  secrets/                # SEC-03B: SecretProvider
  security/               # SEC-01/04: auth, scopes, rate limit
  telemetry.py            # OPS-06: Prometheus instruments
tests/
  unit/                   # 116 tests — handlers, middleware, models, audit
  contract/               # 29 tests — every RPC vs OpenAPI schema
  e2e/                    # 3 tests — runs samples/* against live uvicorn
samples/
  backend/                # scheduled-job-style consumer
  script/                 # interactive exploration script
  llm/                    # Anthropic-shape tool definitions
docs/
  openapi.json            # canonical contract snapshot
  rpcs/                   # auto-generated per-RPC pages
  versioning-policy.md    # OPS-07
tools/
  dump_openapi.py         # regenerates docs/openapi.json
  generate_rpc_docs.py    # regenerates docs/rpcs/
.github/workflows/
  ci.yml                  # lint, mypy, unit (3.11/3.12/3.13), contract, e2e
  openapi.yml             # snapshot freshness + breaking-change diff
```

## Testing

```bash
pytest                    # all 148 tests
pytest tests/unit         # fast unit tests
pytest tests/contract     # OpenAPI schema conformance
pytest tests/e2e          # subprocess sample tests against live uvicorn
ruff check . && ruff format --check .
```

After adding or changing an RPC:

```bash
python tools/dump_openapi.py        # regenerate docs/openapi.json
python tools/generate_rpc_docs.py   # regenerate docs/rpcs/
```

CI verifies both regenerations are up to date.

## Versioning and breaking changes

Per-RPC semver lives on `RpcDescriptor.version` and is surfaced via `describe_catalog`. The `openapi-diff` CI gate flags breaking changes against the merged base; PRs with breaking changes must carry the `breaking-change` label. Full policy: [docs/versioning-policy.md](docs/versioning-policy.md).

## License

MIT
