"""Stage-4 MCP structured tool output on FastMCP + Pydantic.

Stages 1–3 covered tools, resources/prompts, and Context progress. Hosts also
need **typed results**, not only free-form text. Return a Pydantic model (or a
plain dict) from `@mcp.tool`; FastMCP advertises `output_schema` on
`tools/list` and fills `structured_content` on `tools/call`.

Server-initiated sampling / imperative elicitation need a back-channel that
the `2026-07-28` era dropped (SEP-2577 / SEP-2322). Structured output stays
current and teachable on the same FastMCP + Pydantic stack — no extra deps.

Scope: **Python-authored** tools in this lab. C++-exported tools (CppReflectKit)
need an explicit Python result model to match `output_schema`; that friction is
why reflect-kit should not force structured_output — this stage is not a
prescription for that path.

Run as a stdio process (desktop hosts spawn this file):

    python server.py

Or import `mcp` and pass it to `fastmcp.Client(mcp)` for an in-process lab.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("lab-structured-output")


class SumResult(BaseModel):
    """Structured sum for hosts that read `output_schema` / `structured_content`."""

    total: Annotated[float, Field(description="a + b")]
    expression: Annotated[str, Field(description="Human-readable a + b = total")]


class LabelResult(BaseModel):
    """Tiny classifier-shaped payload (label + confidence)."""

    label: Annotated[str, Field(description="Predicted label")]
    confidence: Annotated[float, Field(description="0..1 confidence", ge=0.0, le=1.0)]
    topic: Annotated[str, Field(description="Echo of the input topic")]


@mcp.tool
def sum_pair(
    a: Annotated[float, Field(description="Left operand")],
    b: Annotated[float, Field(description="Right operand")],
) -> SumResult:
    """Add two numbers and return a structured SumResult."""
    total = a + b
    return SumResult(total=total, expression=f"{a} + {b} = {total}")


@mcp.tool
def label_topic(
    topic: Annotated[str, Field(description="Topic keyword to label")],
) -> LabelResult:
    """Return a structured label for a topic (demo heuristic, not an LLM)."""
    key = topic.strip().lower()
    if "mcp" in key:
        label, confidence = "protocol", 0.9
    elif "python" in key:
        label, confidence = "language", 0.85
    else:
        label, confidence = "other", 0.55
    return LabelResult(label=label, confidence=confidence, topic=topic)


if __name__ == "__main__":
    mcp.run()
