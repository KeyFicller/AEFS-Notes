"""Drive completion/complete for prompts and resource templates.

The Client owns protocol negotiation (default: 2026-07-28) and framing.
This demo uses an in-process `Client(mcp)` so the notebook / CLI stay
self-contained; the same API works against `python server.py` over stdio.

Usage:

    python client.py
    python client.py genre --value s
    python client.py topic --genre sci-fi --value m
    python client.py slug --value a
"""

from __future__ import annotations

import argparse
import asyncio

from fastmcp import Client
from mcp_types import PromptReference, ResourceTemplateReference

from server import mcp


async def demo(mode: str, value: str, genre: str) -> None:
    async with Client(mcp) as client:
        print("protocol →", client.protocol_version)
        print("server →", client.server_info.name if client.server_info else None)
        caps = client.server_capabilities
        print("completions →", caps.completions is not None if caps else False)

        if mode == "genre":
            result = await client.complete(
                PromptReference(name="essay"),
                argument={"name": "genre", "value": value},
            )
            print("completion/complete(genre) →", result.values)
        elif mode == "topic":
            result = await client.complete(
                PromptReference(name="essay"),
                argument={"name": "topic", "value": value},
                context_arguments={"genre": genre},
            )
            print(f"completion/complete(topic|genre={genre}) →", result.values)
        else:
            result = await client.complete(
                ResourceTemplateReference(uri="note://{slug}"),
                argument={"name": "slug", "value": value},
            )
            print(
                "completion/complete(slug) →",
                result.values,
                f"total={result.total}",
                f"has_more={result.has_more}",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="genre",
        choices=("genre", "topic", "slug"),
    )
    parser.add_argument("--value", default="s")
    parser.add_argument("--genre", default="sci-fi")
    args = parser.parse_args()
    asyncio.run(demo(args.mode, args.value, args.genre))


if __name__ == "__main__":
    main()
