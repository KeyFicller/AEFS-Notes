"""Drive resources/list → resources/read and prompts/list → prompts/get.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py read --uri note://alpha
    python client.py prompt --topic "MCP resources"
"""

from __future__ import annotations

import argparse
import asyncio

from fastmcp import Client

from server import mcp


async def demo(mode: str, uri: str, topic: str) -> None:
    async with Client(mcp) as client:
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)

        resources = await client.list_resources()
        print("resources/list →", [str(r.uri) for r in resources])

        templates = await client.list_resource_templates()
        print(
            "resources/templates/list →",
            [t.uri_template for t in templates],
        )

        prompts = await client.list_prompts()
        print("prompts/list →", [p.name for p in prompts])

        if mode == "read":
            contents = await client.read_resource(uri)
            text = contents[0].text if contents else None
            print("resources/read →", text)
        else:
            result = await client.get_prompt("critique", {"topic": topic})
            msg = result.messages[0].content.text if result.messages else None
            print("prompts/get →", msg)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="read",
        choices=("read", "prompt"),
    )
    parser.add_argument("--uri", default="lab://greeting")
    parser.add_argument("--topic", default="MCP resources")
    args = parser.parse_args()
    asyncio.run(demo(args.mode, args.uri, args.topic))


if __name__ == "__main__":
    main()
