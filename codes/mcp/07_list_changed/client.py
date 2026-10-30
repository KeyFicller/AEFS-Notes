"""Drive list_changed + resource updated via MessageHandler.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
Pass `message_handler=` so `notifications/tools/list_changed` and
`notifications/resources/updated` reach the host. On each signal the host
refetches (`list_tools` / `read_resource`) — notifications carry no payload
catalog.

This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py demo
    python client.py unlock
    python client.py post --text hello
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from fastmcp import Client
from fastmcp.client.messages import MessageHandler
from mcp.types import (
    ResourceUpdatedNotification,
    ToolListChangedNotification,
)

from server import BOARD_URI, mcp


class LabHandler(MessageHandler):
    """Collect change notifications; print one line each."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_tool_list_changed(
        self, message: ToolListChangedNotification
    ) -> None:
        self.events.append("tools/list_changed")
        print("notify → tools/list_changed")

    async def on_resource_updated(
        self, message: ResourceUpdatedNotification
    ) -> None:
        uri = str(message.params.uri)
        self.events.append(f"resources/updated:{uri}")
        print(f"notify → resources/updated {uri}")


async def _text(result: Any) -> str | None:
    if getattr(result, "content", None):
        return result.content[0].text
    return getattr(result, "data", None)


async def demo() -> None:
    handler = LabHandler()
    async with Client(mcp, message_handler=handler) as client:
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)

        tools = await client.list_tools()
        print("tools/list (before) →", [t.name for t in tools])

        board = await client.read_resource(BOARD_URI)
        print("resources/read (before) →", board[0].text if board else None)

        unlock = await client.call_tool("unlock_secret", {})
        print("tools/call(unlock_secret) →", await _text(unlock))
        # Session notifications can arrive just after the call returns.
        await asyncio.sleep(0.05)
        tools = await client.list_tools()
        print("tools/list (after unlock) →", [t.name for t in tools])

        secret = await client.call_tool("secret_ping", {})
        print("tools/call(secret_ping) →", await _text(secret))

        posted = await client.call_tool("post_board", {"text": "stage-7"})
        print("tools/call(post_board) →", await _text(posted))
        await asyncio.sleep(0.05)
        board = await client.read_resource(BOARD_URI)
        print("resources/read (after post) →", board[0].text if board else None)

        print("events →", handler.events)


async def unlock_only() -> None:
    handler = LabHandler()
    async with Client(mcp, message_handler=handler) as client:
        print("protocol →", client.protocol_version)
        print("tools/list (before) →", [t.name for t in await client.list_tools()])
        result = await client.call_tool("unlock_secret", {})
        print("tools/call(unlock_secret) →", await _text(result))
        await asyncio.sleep(0.05)
        print("tools/list (after) →", [t.name for t in await client.list_tools()])
        print("events →", handler.events)


async def post_only(text: str) -> None:
    handler = LabHandler()
    async with Client(mcp, message_handler=handler) as client:
        print("protocol →", client.protocol_version)
        before = await client.read_resource(BOARD_URI)
        print("resources/read (before) →", before[0].text if before else None)
        result = await client.call_tool("post_board", {"text": text})
        print("tools/call(post_board) →", await _text(result))
        await asyncio.sleep(0.05)
        after = await client.read_resource(BOARD_URI)
        print("resources/read (after) →", after[0].text if after else None)
        print("events →", handler.events)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="demo",
        choices=("demo", "unlock", "post"),
    )
    parser.add_argument("--text", default="hello")
    args = parser.parse_args()

    if args.mode == "demo":
        asyncio.run(demo())
    elif args.mode == "unlock":
        asyncio.run(unlock_only())
    else:
        asyncio.run(post_only(args.text))


if __name__ == "__main__":
    main()
