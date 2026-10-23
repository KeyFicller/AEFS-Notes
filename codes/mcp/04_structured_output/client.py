"""Drive tools/list → tools/call and print structured results.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py sum --a 2 --b 3
    python client.py label --topic "MCP structured"
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from fastmcp import Client

from server import mcp


def _as_mapping(result: Any) -> Any:
    """Prefer structured_content; fall back to result.data."""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    data = getattr(result, "data", None)
    if data is not None and hasattr(data, "model_dump"):
        return data.model_dump()
    return data


async def demo(tool: str, arguments: dict[str, Any]) -> None:
    async with Client(mcp) as client:
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)

        tools = await client.list_tools()
        print("tools/list →", [t.name for t in tools])
        for t in tools:
            print(f"  {t.name}.output_schema →", t.output_schema)

        result = await client.call_tool(tool, arguments)
        print("tools/call.structured →", _as_mapping(result))
        text = result.content[0].text if result.content else None
        print("tools/call.text →", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", default="sum", choices=["sum", "label"])
    parser.add_argument("--a", type=float, default=2.0)
    parser.add_argument("--b", type=float, default=3.0)
    parser.add_argument("--topic", default="MCP structured")
    args = parser.parse_args()

    if args.tool == "sum":
        asyncio.run(demo("sum_pair", {"a": args.a, "b": args.b}))
    else:
        asyncio.run(demo("label_topic", {"topic": args.topic}))


if __name__ == "__main__":
    main()
