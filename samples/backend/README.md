# Backend service-account sample

A scheduled-job style consumer that calls `/rpc/partner_revenue` and prints
or writes the result.

```bash
pip install httpx
export CONNECTOR_URL=http://localhost:8000
export CONNECTOR_API_KEY=<service-account-key>
python partner_revenue_job.py            # stdout
python partner_revenue_job.py out.json   # write to file
```

The response carries the typed envelope:

```json
{
  "data": { "rows": [...] },
  "meta": {
    "freshness_window_days": 60,
    "source_question_id": <card_id>,
    "kind": "catalog",
    "request_id": "..."
  }
}
```

The `freshness_window_days` field is the eventual-consistency caveat —
recent data within that window may shift on re-run.
