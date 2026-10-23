"""Minimal NDJSON JSON-RPC tools server (teaching subset of MCP).

Real MCP stdio uses Content-Length framed messages. This lab uses one JSON
object per line so every request/response is easy to print and debug.

Supported methods:
  - initialize
  - tools/list
  - tools/call

Run as a process (the client spawns this file):

    python server.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable


PROTOCOL_VERSION = "2024-11-05"


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]


def _echo(arguments: dict[str, Any]) -> str:
    return str(arguments.get("text", ""))


def _add(arguments: dict[str, Any]) -> str:
    left = float(arguments.get("a", 0))
    right = float(arguments.get("b", 0))
    return str(left + right)


TOOLS: dict[str, Tool] = {
    "echo": Tool(
        name="echo",
        description="Return the given text unchanged.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_echo,
    ),
    "add": Tool(
        name="add",
        description="Add two numbers and return the sum as text.",
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        handler=_add,
    ),
}


def ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def err(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch one JSON-RPC message. Notifications (no id) return None."""
    method = message.get("method")
    request_id = message.get("id", None)
    params = message.get("params") or {}

    if method == "initialize":
        return ok(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "lab-tools-server", "version": "0.1.0"},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in TOOLS.values()
        ]
        return ok(request_id, {"tools": tools})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tool = TOOLS.get(name)
        if tool is None:
            return err(request_id, -32602, f"Unknown tool: {name!r}")
        try:
            text = tool.handler(arguments)
        except Exception as exc:  # noqa: BLE001 - surface as JSON-RPC error for the lab
            return err(request_id, -32000, f"Tool failed: {exc}")
        return ok(
            request_id,
            {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            },
        )

    if request_id is None:
        return None
    return err(request_id, -32601, f"Method not found: {method!r}")


def main() -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = err(None, -32700, f"Parse error: {exc}")
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
