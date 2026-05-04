# metabase-connector

Typed-RPC HTTP service fronting Metabase. A curated catalog of analytical RPCs (`partner_revenue`, `channel_split`, `mrr_trend`, `arr_at_risk`, `upsell_opportunities`, `revenue_comparison`, `data_quality_signals`, `license_query`, `top_partners`, `describe_catalog`) backed by saved Metabase questions.

Saved questions are authored and managed in Metabase directly; this service references them by card ID via config and exposes them as a typed HTTP contract with auth, scopes, audit logging, and a response-metadata envelope.

## Status

v0 — runtime skeleton. Card IDs not yet wired; integration tests run against a stubbed Metabase.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # edit METABASE_URL and credentials
uvicorn connector.app:app --reload
```

Then:

```bash
curl http://localhost:8000/healthz
```

## Layout

```
src/connector/        # runtime
  app.py              # FastAPI app
  settings.py         # env-loaded config
  errors.py           # typed error envelope
  registry.py         # RpcDescriptor + registry
  middleware/         # request-id, auth, scope, audit, ratelimit
  clients/metabase.py # Metabase HTTP client
  rpcs/               # one file per catalog RPC
  models/             # Response[T], ResponseMeta, ConsumerType
tests/                # unit, contract, integration, e2e
samples/              # consumer code (backend, script, llm)
docs/                 # OpenAPI snapshot, per-RPC docs
```

## Contract surface

Every RPC response is shaped:

```json
{
  "data": <typed payload>,
  "meta": {
    "freshness_window_days": 60,
    "source_question_id": 159,
    "kind": "catalog",
    "request_id": "..."
  }
}
```

Errors are uniform:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "...",
  "request_id": "...",
  "debug": { ... }
}
```

## License

MIT
