# MCP staged practice

Exercises live in `codes/mcp/{stage}/qa.ipynb`. When a stage needs files on
disk, that stage directory is the workspace.

Stage 1 uses **FastMCP + Pydantic**: you write typed tool functions; the
framework owns JSON Schema generation and the MCP protocol (default era
`2026-07-28`). The conceptual loop stays `connect → list_tools → call_tool`
— the same initialize / tools/list / tools/call agents rely on, without
hand-rolling envelopes.

| Stage | Directory | Focus |
| --- | --- | --- |
| 1 | `01_fastmcp_tools` | FastMCP server, Pydantic/`Field` schemas, Client list/call loop |
| 2 | *(planned)* `02_resources_prompts` | `resources` / `prompts` on the same FastMCP server |
| 3 | *(planned)* `03_stdio_host` | Run `server.py` under a real desktop host / Inspector |
| 4 | *(planned)* `04_http_remote` | HTTP transport for a remote MCP endpoint |

Honesty note: stage 1 is still a **lab**. It teaches the tools loop on
FastMCP defaults; it is not a production deployment guide.
