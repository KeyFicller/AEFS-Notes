# MCP staged practice

Exercises live in `codes/mcp/{stage}/qa.ipynb`. When a stage needs files on
disk, that stage directory is the workspace.

This track starts from the wire: JSON-RPC messages in, tool results out. The
`references/` notebook sketches a newer discover / subscription shape; stage 1
implements the stable tools loop that agents actually call today.

| Stage | Directory | Focus |
| --- | --- | --- |
| 1 | `01_jsonrpc_tools` | NDJSON JSON-RPC over stdio, `initialize`, `tools/list`, `tools/call`, register a tool |
| 2 | *(planned)* `02_content_length_stdio` | Upgrade framing to MCP Content-Length headers |
| 3 | *(planned)* `03_resources_prompts` | `resources/list` / `read`, `prompts/list` / `get` |
| 4 | *(planned)* `04_official_sdk` | Same server shape on the official MCP Python SDK |

Honesty note: stage 1 is a **teaching subset**, not a full MCP server. It keeps
the method names and result shapes close to MCP so later stages can swap the
transport without rewriting the tool handlers.
