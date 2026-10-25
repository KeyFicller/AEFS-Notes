"""Stage-2 A2A server: FastA2A + framework-agnostic Worker.

Stage 1 showed the A2A 1.0.1 wire with stdlib. This stage lets FastA2A
(Starlette ASGI + Pydantic schemas) own the JSON-RPC surface while we
only implement a Worker. No pydantic-ai / LLM stack — the teaching point
is the framework shape (Storage + Broker + Worker), not a model call.

Run:

    python server.py                 # http://127.0.0.1:41243
    python server.py --port 41243

Endpoints (what FastA2A 2.x exposes):
  GET  /.well-known/agent-card.json
  POST /                            (JSON-RPC: message/send, tasks/get, …)
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fasta2a import FastA2A, Worker
from fasta2a.broker import InMemoryBroker
from fasta2a.schema import Artifact, Message, Part, Skill, TaskIdParams, TaskSendParams
from fasta2a.storage import InMemoryStorage

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 41243

Context = list[Message]


class SummaryWorker(Worker[Context]):
    """Deterministic writer-agent Worker — no LLM.

    FastA2A always creates a *new* Task per `message/send`. Conversation
    continuity is the `context_id`: we stash prior turns in Storage and
    read them on the next task that shares the same context.
    """

    async def run_task(self, params: TaskSendParams) -> None:
        task = await self.storage.load_task(params["id"])
        assert task is not None
        await self.storage.update_task(task["id"], state="working")

        context: Context = await self.storage.load_context(task["context_id"]) or []
        history = list(task.get("history") or [])
        context.extend(history)

        length = _extract_target_length(context)
        if length is None:
            ask = Message(
                role="agent",
                parts=[
                    Part(
                        text=(
                            "Please send a data part with targetLength "
                            "(e.g. '3 paragraphs')."
                        )
                    )
                ],
                message_id=str(uuid.uuid4()),
            )
            context.append(ask)
            await self.storage.update_context(task["context_id"], context)
            await self.storage.update_task(
                task["id"], state="input-required", new_messages=[ask]
            )
            return

        source = _extract_source_text(context) or "(no source text)"
        summary = (
            f"[fasta2a-worker] length={length}\n"
            f"source={source[:120]}\n"
            "Done."
        )
        reply = Message(
            role="agent",
            parts=[Part(text="Summary ready.")],
            message_id=str(uuid.uuid4()),
        )
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            name="summary",
            parts=[Part(text=summary, media_type="text/markdown")],
        )
        context.append(reply)
        await self.storage.update_context(task["context_id"], context)
        await self.storage.update_task(
            task["id"],
            state="completed",
            new_messages=[reply],
            new_artifacts=[artifact],
        )

    async def cancel_task(self, params: TaskIdParams) -> None:
        await self.storage.update_task(params["id"], state="canceled")

    def build_message_history(self, history: list[Message]) -> list[Any]:
        # Unused by this Worker (we write Storage ourselves); required abstract.
        return list(history)

    def build_artifacts(self, result: Any) -> list[Artifact]:
        return []


def _extract_target_length(messages: list[Message]) -> str | None:
    for msg in reversed(messages):
        for part in msg.get("parts") or []:
            data = part.get("data")
            if isinstance(data, dict) and "targetLength" in data:
                return str(data["targetLength"])
    return None


def _extract_source_text(messages: list[Message]) -> str | None:
    for msg in messages:
        if msg.get("role") != "user":
            continue
        for part in msg.get("parts") or []:
            text = part.get("text")
            if text:
                return text
    return None


def build_app(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> FastA2A:
    """Build the FastA2A ASGI app (Storage + Broker + Worker lifespan)."""
    storage = InMemoryStorage()
    broker = InMemoryBroker()
    worker = SummaryWorker(storage=storage, broker=broker)
    base_url = f"http://{host}:{port}"

    @asynccontextmanager
    async def lifespan(app: FastA2A) -> AsyncIterator[None]:
        # TaskManager must be entered so HTTP handlers can schedule work;
        # worker.run() drains the broker in the background.
        async with app.task_manager:
            async with worker.run():
                yield

    return FastA2A(
        storage=storage,
        broker=broker,
        lifespan=lifespan,
        name="writer-agent",
        description="Drafts a short technical summary (FastA2A lab).",
        version="1.0.0",
        url=base_url,
        skills=[
            Skill(
                id="draft_summary",
                name="Draft summary",
                description=(
                    "Given source text and a targetLength, produce a short summary."
                ),
                tags=["writing", "summarization"],
                input_modes=["text/plain", "application/json"],
                output_modes=["text/markdown"],
            )
        ],
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/markdown"],
        docs_url=None,
    )


# Module-level app for `uvicorn server:app` (uses default host/port in the card URL).
app = build_app()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    import uvicorn

    # Rebuild so the Agent Card URL matches the listen address.
    asgi = build_app(host=args.host, port=args.port)
    uvicorn.run(asgi, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
