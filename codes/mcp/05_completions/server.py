"""Stage-5 MCP argument completions on FastMCP + Pydantic.

Stages 1–4 covered tools, resources/prompts, Context progress, and structured
tool output. Hosts that fill prompt args or resource-template placeholders
also need **prefix completions**. Register one `@mcp.completion` handler;
FastMCP advertises the `completions` capability and answers
`completion/complete` for:

- `PromptReference` — prompt argument names
- `ResourceTemplateReference` — URI-template placeholders

Return a `list[str]`, a `Completion` (with optional `total` / `has_more`), or
`None` when the reference/argument is not yours (empty completion, not an
error). Multi-arg prompts can read already-filled values via the handler's
`context` / the client's `context_arguments`.

This stays current on the `2026-07-28` era — no sampling back-channel, no
deprecated protocol logging. Same FastMCP + Pydantic stack; no extra deps.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp_types import (
    Completion,
    PromptReference,
    ResourceTemplateReference,
)
from pydantic import Field

mcp = FastMCP("lab-completions")

# Prompt-arg candidates keyed by genre (context-aware topic completion).
TOPICS_BY_GENRE: dict[str, list[str]] = {
    "sci-fi": ["mars", "android", "wormhole"],
    "mystery": ["manor", "alibi", "cipher"],
    "nature": ["forest", "tide", "summit"],
}

# Resource-template slug candidates.
NOTE_SLUGS = ["alpha", "beta", "gamma", "atlas", "aurora"]


@mcp.prompt
def essay(
    genre: Annotated[str, Field(description="Essay genre")],
    topic: Annotated[str, Field(description="Topic within the chosen genre")],
) -> str:
    """Build a short essay prompt; args are completion targets."""
    return f"Write a short {genre} essay about {topic}."


@mcp.resource("note://{slug}", mime_type="text/markdown")
def note(slug: str) -> str:
    """Templated note: clients complete `{slug}` then read `note://…`."""
    return f"# note:{slug}\nbody for {slug}"


@mcp.completion
def complete(ref, argument, context):
    """Answer completion/complete for essay args and note://{slug}."""
    prefix = argument.value or ""

    if isinstance(ref, PromptReference) and ref.name == "essay":
        filled = (context.arguments if context else None) or {}
        if argument.name == "genre":
            return [g for g in TOPICS_BY_GENRE if g.startswith(prefix)]
        if argument.name == "topic":
            genre = filled.get("genre", "")
            options = TOPICS_BY_GENRE.get(genre, [])
            return [t for t in options if t.startswith(prefix)]
        return None

    if isinstance(ref, ResourceTemplateReference) and ref.uri == "note://{slug}":
        if argument.name == "slug":
            values = [s for s in NOTE_SLUGS if s.startswith(prefix)]
            return Completion(values=values, total=len(values), has_more=False)
        return None

    return None


if __name__ == "__main__":
    mcp.run()
