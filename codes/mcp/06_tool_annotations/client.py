"""Drive tools/list and print ToolAnnotations / _meta, then call one tool.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py list
    python client.py peek --slug alpha
    python client.py append --slug gamma --text hello
    python client.py wipe --slug gamma --confirm
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from fastmcp import Client

from server import mcp


def _ann_dict(tool: Any) -> dict[str, Any]:
    ann = getattr(tool, "annotations", None)
    if ann is None:
        return {}
    if hasattr(ann, "model_dump"):
        return ann.model_dump(exclude_none=True)
    if isinstance(ann, dict):
        return dict(ann)
    return {"repr": repr(ann)}


async def list_tools() -> None:
    async with Client(mcp) as client:
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)
        tools = await client.list_tools()
        print("tools/list →", [t.name for t in tools])
        for t in tools:
            print(f"  {t.name}")
            print(f"    description →", t.description)  # model-facing (docstring)
            print(f"    title →", getattr(t, "title", None))  # UI label (annotations.title)
            print(f"    annotations →", _ann_dict(t))
            print(f"    meta →", getattr(t, "meta", None))


async def call(tool: str, arguments: dict[str, Any]) -> None:
    async with Client(mcp) as client:
        print("protocol →", client.protocol_version)
        result = await client.call_tool(tool, arguments)
        text = result.content[0].text if result.content else None
        print(f"tools/call({tool}) →", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="list",
        choices=("list", "peek", "append", "wipe"),
    )
    parser.add_argument("--slug", default="alpha")
    parser.add_argument("--text", default="hello")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    if args.mode == "list":
        asyncio.run(list_tools())
    elif args.mode == "peek":
        asyncio.run(call("peek_note", {"slug": args.slug}))
    elif args.mode == "append":
        asyncio.run(call("append_note", {"slug": args.slug, "text": args.text}))
    else:
        asyncio.run(call("wipe_note", {"slug": args.slug, "confirm": args.confirm}))


if __name__ == "__main__":
    main()
