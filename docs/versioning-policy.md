# Versioning policy

## Per-RPC semver

Every RPC carries a `version` field on its `RpcDescriptor`, surfaced via
`/rpc/describe_catalog` and the OpenAPI document.

- **Patch** (`1.0.0 → 1.0.1`) — bug fixes that don't change request or response
  shape (e.g., a wrong column name in a reshape; a fix to a parameter
  cross-validator).
- **Minor** (`1.0.0 → 1.1.0`) — additive changes: a new optional input field,
  a new optional output field, a new RPC. Existing consumers keep working.
- **Major** (`1.0.0 → 2.0.0`) — breaking changes: removing or renaming a
  field, narrowing an enum, changing the type of an existing field, removing
  an RPC.

When introducing a major change:

1. Bump the per-RPC `version` field.
2. Set `deprecated_at` on the previous descriptor with a sunset date.
3. Update `docs/openapi.json` via `python tools/dump_openapi.py`.
4. The `openapi-diff` CI gate will flag breaking changes; the PR must
   carry the `breaking-change` label to pass.

## Deprecation path

Mark `deprecated_at` (ISO-8601 timestamp) on `RpcDescriptor`. Consumers see
the field in `describe_catalog`. Recommended sunset window: **90 days**
between deprecation and removal.

## OpenAPI snapshot

`docs/openapi.json` is a committed snapshot of the connector's contract.
Regenerate with `python tools/dump_openapi.py` whenever Pydantic models
or registry entries change. CI verifies the snapshot matches runtime so
drift cannot land silently.

## What counts as breaking

| Change | Breaking? |
|---|---|
| New optional field on input or output | No |
| New RPC | No |
| Field default value changed | Maybe — depends on consumer assumptions |
| Required field added to input | **Yes** |
| Required field removed from output | **Yes** |
| Field renamed | **Yes** |
| Field type narrowed (e.g., string → enum) | **Yes** |
| Enum value removed | **Yes** |
| Enum value added | No (consumers should handle unknown variants) |
| RPC removed | **Yes** |
| `required_scope` widened (e.g., general → operator) | **Yes** |
| Error envelope shape change | **Yes** |
| Response envelope shape change | **Yes** |

## Communication

Breaking changes are announced via:

1. The `breaking-change` PR label and PR description.
2. `deprecated_at` on the affected descriptor.
3. A note in the release tag's release notes.

There is no `Sunset` HTTP header in v1; revisit if consumers need machine-
readable deprecation signals.
