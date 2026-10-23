"""Drive tools/call while capturing progress notifications.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
Pass `progress_handler` so mid-call `notifications/progress` reach the host.
This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py --n 4
"""

from __future__ import annotations

import argparse
import asyncio

from fastmcp import Client

from server import mcp


async def on_progress(
    progress: float,
    total: float | None,
    message: str | None,
) -> None:
    if total not in (None, 0):
        pct = 100.0 * progress / total
        print(f"progress → {progress}/{total} ({pct:.0f}%) {message or ''}".rstrip())
    else:
        print(f"progress → {progress} {message or ''}".rstrip())


async def demo(n: int) -> None:
    async with Client(mcp, progress_handler=on_progress) as client:
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)

        tools = await client.list_tools()
        print("tools/list →", [t.name for t in tools])
        # Context is injected by FastMCP — it must not appear in input_schema.
        schema = tools[0].input_schema
        print("input_schema.properties →", sorted(schema.get("properties", {})))

        result = await client.call_tool("count_up", {"n": n})
        text = result.content[0].text if result.content else result.data
        print("tools/call →", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(demo(args.n))


if __name__ == "__main__":
    main()
