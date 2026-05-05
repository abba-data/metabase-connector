"""Render docs/rpcs/<name>.md from the registered RpcDescriptors.

Each page is a deterministic flatten of input and output JSON Schemas,
the required scope, freshness window, and the source-question id (if any).
Re-run after adding or changing an RPC. The pages are an authoritative
human-readable companion to /rpc/describe_catalog.

Usage:
  python tools/generate_rpc_docs.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        ref = schema["$ref"]
        return _resolve(components[ref.split("/")[-1]], components)
    return schema


def _type_for(prop: dict[str, Any], components: dict[str, Any]) -> str:
    p = _resolve(prop, components)
    if "anyOf" in p:
        opts = [_type_for(o, components) for o in p["anyOf"]]
        return " | ".join(o for o in opts if o != "null")
    if "enum" in p:
        return "{" + ", ".join(repr(v) for v in p["enum"]) + "}"
    if p.get("type") == "array":
        items = _type_for(p.get("items", {}), components)
        return f"list[{items}]"
    if p.get("type") == "object":
        return "object"
    return p.get("type", "any")


def _properties_table(
    schema: dict[str, Any], components: dict[str, Any], indent: int = 0
) -> list[str]:
    s = _resolve(schema, components)
    required = set(s.get("required", []))
    props = s.get("properties", {})
    if not props:
        return ["_(none)_"]
    lines = ["| Field | Type | Required | Description |", "|---|---|---|---|"]
    for name, prop in props.items():
        p = _resolve(prop, components)
        typ = _type_for(prop, components)
        req = "yes" if name in required else "no"
        desc = (p.get("description") or "").replace("\n", " ").replace("|", "\\|")
        default = p.get("default")
        if default is not None and not isinstance(default, dict):
            desc = f"{desc} (default `{default}`)" if desc else f"default `{default}`"
        lines.append(f"| `{name}` | `{typ}` | {req} | {desc} |")
    return lines


def render_rpc_page(entry: dict[str, Any], components: dict[str, Any]) -> str:
    name = entry["name"]
    parts: list[str] = []
    parts.append(f"# {name}")
    parts.append("")
    parts.append(
        f"> v{entry['version']} · scope `{entry['required_scope']}` · "
        f"freshness {entry['freshness_window_days']}d"
    )
    parts.append("")
    parts.append(entry["description"])
    parts.append("")
    if entry.get("source_question_id"):
        parts.append(f"**Source Metabase card:** `{entry['source_question_id']}`")
        parts.append("")
    parts.append("## Input")
    parts.append("")
    parts.extend(_properties_table(entry["input_schema"], components))
    parts.append("")
    if entry.get("output_schema"):
        parts.append("## Output (`data` field)")
        parts.append("")
        parts.extend(_properties_table(entry["output_schema"], components))
        parts.append("")
    parts.append("## Response envelope")
    parts.append("")
    parts.append("Every response wraps the data above:")
    parts.append("")
    parts.append("```json")
    parts.append("{")
    parts.append('  "data": { ... },')
    parts.append('  "meta": {')
    parts.append(f'    "freshness_window_days": {entry["freshness_window_days"]},')
    sqid = entry.get("source_question_id")
    parts.append(f'    "source_question_id": {sqid if sqid else "null"},')
    parts.append('    "kind": "catalog",')
    parts.append('    "request_id": "..."')
    parts.append("  }")
    parts.append("}")
    parts.append("```")
    parts.append("")
    parts.append("## Example")
    parts.append("")
    parts.append("```bash")
    parts.append(f"curl -X POST $CONNECTOR_URL/rpc/{name} \\")
    parts.append('  -H "X-Connector-API-Key: $CONNECTOR_API_KEY" \\')
    parts.append('  -H "Content-Type: application/json" \\')
    parts.append("  -d '{}'")
    parts.append("```")
    parts.append("")
    return "\n".join(parts)


def render_index(entries: list[dict[str, Any]]) -> str:
    parts = [
        "# RPC catalog",
        "",
        "Auto-generated. Re-run `python tools/generate_rpc_docs.py` after RPC changes.",
        "",
    ]
    parts.append("| RPC | Version | Scope | Freshness | Card |")
    parts.append("|---|---|---|---|---|")
    for e in entries:
        card = e.get("source_question_id") or "—"
        parts.append(
            f"| [`{e['name']}`]({e['name']}.md) | {e['version']} | "
            f"{e['required_scope']} | {e['freshness_window_days']}d | {card} |"
        )
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    os.environ.setdefault("AUDIT_STORE", "memory")
    os.environ.setdefault("CONNECTOR_API_KEYS", "")
    from connector.app import create_app
    from connector.audit.store import InMemoryAuditStore
    from connector.registry import registry

    create_app(audit_store=InMemoryAuditStore())  # populates registry

    out_dir = Path("docs/rpcs")
    out_dir.mkdir(parents=True, exist_ok=True)

    components: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    for d in registry.all():
        input_schema = d.input_model.model_json_schema(ref_template="#/$defs/{model}")
        output_schema = (
            d.output_model.model_json_schema(ref_template="#/$defs/{model}")
            if d.output_model
            else None
        )
        # Pydantic emits $defs alongside the schema; flatten for the renderer.
        for k, v in (input_schema.get("$defs") or {}).items():
            components[k] = v
        if output_schema:
            for k, v in (output_schema.get("$defs") or {}).items():
                components[k] = v
        entries.append(
            {
                "name": d.name,
                "version": d.version,
                "description": d.description,
                "required_scope": d.required_scope.value,
                "freshness_window_days": d.freshness_window_days,
                "source_question_id": d.metabase_card_id,
                "input_schema": input_schema,
                "output_schema": output_schema,
            }
        )

    # Patch components to use $defs refs uniformly.
    components_for_render = {k: _rewrite(v) for k, v in components.items()}

    for entry in entries:
        page = render_rpc_page(
            {**entry, "input_schema": _rewrite(entry["input_schema"])},
            components_for_render,
        )
        if entry.get("output_schema"):
            page = render_rpc_page(
                {
                    **entry,
                    "input_schema": _rewrite(entry["input_schema"]),
                    "output_schema": _rewrite(entry["output_schema"]),
                },
                components_for_render,
            )
        (out_dir / f"{entry['name']}.md").write_text(page)

    (out_dir / "README.md").write_text(render_index(entries))
    print(f"wrote {len(entries) + 1} files to {out_dir}/")
    return 0


def _rewrite(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: (
                v.replace("#/components/schemas/", "#/$defs/")
                if k == "$ref" and isinstance(v, str)
                else _rewrite(v)
            )
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_rewrite(v) for v in node]
    return node


if __name__ == "__main__":
    sys.exit(main())
