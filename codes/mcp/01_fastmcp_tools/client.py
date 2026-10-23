"""Drive initialize → tools/list → tools/call via FastMCP Client.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py add --a 2 --b 3
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from fastmcp import Client

from server import mcp


async def demo(tool: str, arguments: dict[str, Any]) -> None:
    async with Client(mcp) as client:
        # Protocol negotiation already happened when the context entered.
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)

        tools = await client.list_tools()
        print("tools/list →", [t.name for t in tools])

        result = await client.call_tool(tool, arguments)
        text = result.content[0].text if result.content else result.data
        print("tools/call →", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", default="echo")
    parser.add_argument("--text", default="hello MCP")
    parser.add_argument("--a", type=float, default=2.0)
    parser.add_argument("--b", type=float, default=3.0)
    args = parser.parse_args()

    if args.tool == "echo":
        asyncio.run(demo("echo", {"text": args.text}))
    elif args.tool == "add":
        asyncio.run(demo("add", {"a": args.a, "b": args.b}))
    else:
        asyncio.run(demo(args.tool, {}))


if __name__ == "__main__":
    main()
