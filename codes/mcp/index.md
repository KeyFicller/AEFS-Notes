# MCP staged practice

Exercises live in `codes/mcp/{stage}/qa.ipynb`. When a stage needs files on
disk, that stage directory is the workspace.

Stages 1–2 use **FastMCP + Pydantic**: you write typed callables; the
framework owns JSON Schema generation and the MCP protocol (default era
`2026-07-28`). The conceptual loop grows from
`connect → list_tools → call_tool` to also cover
`list_resources / read_resource` and `list_prompts / get_prompt` — still
without hand-rolling envelopes.

| Stage | Directory | Focus |
| --- | --- | --- |
| 1 | `01_fastmcp_tools` | FastMCP server, Pydantic/`Field` schemas, Client list/call loop |
| 2 | `02_resources_prompts` | `@mcp.resource` (static + URI template) and `@mcp.prompt` on the same server |
| 3 | *(planned)* `03_stdio_host` | Run `server.py` under a real desktop host / Inspector |
| 4 | *(planned)* `04_http_remote` | HTTP transport for a remote MCP endpoint |

Honesty note: these stages are still a **lab**. They teach the MCP surface on
FastMCP defaults; they are not a production deployment guide.
