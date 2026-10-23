"""Stage-6 MCP tool annotations + _meta on FastMCP + Pydantic.

Stages 1–5 covered tools, resources/prompts, Context progress, structured
output, and argument completions. Hosts that *decide which tool to offer*
also need **behavior hints** on `tools/list` — not only names and schemas.

Pass `annotations=` (`ToolAnnotations` or a dict) and optional `meta=` on
`@mcp.tool`. FastMCP advertises them on each tool so a host can:

- Prefer `read_only_hint` tools for safe / auto-approve paths
- Gate `destructive_hint` tools behind confirmation
- Treat `idempotent_hint` retries as safe
- Flag `open_world_hint` tools that reach outside the server

`meta` is free-form `_meta` for host UX (category, owner, …). FastMCP may
also attach its own keys under `meta["fastmcp"]` — that is normal, not an
error. This stays current on the `2026-07-28` era — no sampling back-channel,
no deprecated protocol logging. Same FastMCP + Pydantic stack; no extra deps.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

mcp = FastMCP("lab-tool-annotations")

# In-memory scratch notes for the demo tools.
_NOTES: dict[str, str] = {
    "alpha": "first note",
    "beta": "second note",
}


@mcp.tool(
    annotations=ToolAnnotations(
        title="Peek Note",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
    meta={"category": "notes", "risk": "low"},
)
def peek_note(
    slug: Annotated[str, Field(description="Note slug to read")],
) -> str:
    """Read a note without changing server state (safe / auto-approve)."""
    return _NOTES.get(slug, f"(missing:{slug})")


@mcp.tool(
    annotations=ToolAnnotations(
        title="Append Note",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    ),
    meta={"category": "notes", "risk": "medium"},
)
def append_note(
    slug: Annotated[str, Field(description="Note slug to append to")],
    text: Annotated[str, Field(description="Text to append")],
) -> str:
    """Append text to a note (mutates state; not idempotent)."""
    prev = _NOTES.get(slug, "")
    _NOTES[slug] = f"{prev}\n{text}" if prev else text
    return _NOTES[slug]


@mcp.tool(
    annotations={
        "title": "Wipe Note",
        "read_only_hint": False,
        "destructive_hint": True,
        "idempotent_hint": True,
        "open_world_hint": False,
    },
    meta={"category": "notes", "risk": "high"},
)
def wipe_note(
    slug: Annotated[str, Field(description="Note slug to delete")],
    confirm: Annotated[bool, Field(description="Must be true to delete")] = False,
) -> str:
    """Delete a note when confirm=True (destructive; confirm before calling)."""
    if not confirm:
        return "noop"
    existed = slug in _NOTES
    _NOTES.pop(slug, None)
    return "wiped" if existed else "missing"


if __name__ == "__main__":
    mcp.run()
