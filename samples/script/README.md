# Interactive-script sample

Self-discovering exploration script — calls `describe_catalog` first, then
runs a couple of catalog RPCs and prints summary lines. Drop into a terminal
session or a Jupyter cell.

```bash
pip install httpx
export CONNECTOR_URL=http://localhost:8000
export CONNECTOR_API_KEY=<your-key>
python explore.py
```

For a notebook variant, copy `call(...)` and the `httpx.Client` setup into
a cell, then issue ad-hoc calls. Every response carries `meta.request_id`
which you can grep in the connector's audit log via `/rpc/read_audit`
(operator scope) if a result looks off.
