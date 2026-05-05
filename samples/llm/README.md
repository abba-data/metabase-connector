# LLM-agent sample

Translates the connector's `describe_catalog` output into Anthropic-style
tool definitions. The catalog is the only thing the agent needs to know
upfront — schemas, descriptions, and scopes flow from `describe_catalog`,
so adding a new RPC server-side instantly exposes it to the agent.

```python
import anthropic
from samples.llm.tools import build_tools, call_rpc

client = anthropic.Anthropic()
tools = build_tools()

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What's our partner revenue last quarter?"}],
)

# Loop: when response.content has a tool_use block, call connector and
# append the tool_result to messages, then re-call messages.create.
for block in response.content:
    if block.type == "tool_use":
        out = call_rpc(block.name, block.input)
        # ... feed back into the conversation
```

Operator-scope RPCs (`read_audit`) are filtered out by `build_tools()` —
the agent should not drive audit reads. Set `CONNECTOR_API_KEY` to a key
with `general` (and optionally `raw_sql`) scope only.
