"""Stage-1 FastAPI lab: routes + Pydantic + Depends + async SSE + static frontend.

A tiny chat service. The "LLM" is a deterministic mock that emits tokens with
`asyncio.sleep`, so the lab runs anywhere with no API key. The same
`ChatBackend` seam also has an OpenAI-compatible implementation (httpx stream),
selected with `CHAT_BACKEND=openai`.

Run:

    python app.py                    # http://127.0.0.1:8000  (open in a browser)
    python app.py --port 8000

Endpoints:
  GET  /                       the static chat page (static/index.html)
  GET  /api/health             liveness + which backend is wired
  GET  /api/stats              stream counters (started / completed / cancelled)
  POST /api/chat               one-shot JSON reply
  POST /api/chat/stream        Server-Sent Events: `token` ... `done` (or `error`)
  GET  /docs                   Swagger UI generated from the Pydantic models
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Protocol

import httpx
from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


# ---------------------------------------------------------------- schemas ---
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """The server is stateless: the browser sends the whole history each turn."""

    messages: list[Message] = Field(min_length=1, max_length=50)


class ChatResponse(BaseModel):
    reply: str
    tokens: int


# --------------------------------------------------------------- settings ---
@dataclass(frozen=True)
class Settings:
    backend: Literal["mock", "openai"] = "mock"
    token_delay: float = 0.03  # seconds between mock tokens
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    """Read env once. Tests swap it with `app.dependency_overrides`."""
    return Settings(
        backend="openai" if os.getenv("CHAT_BACKEND") == "openai" else "mock",
        token_delay=float(os.getenv("MOCK_TOKEN_DELAY", "0.03")),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )


# --------------------------------------------------------------- backends ---
class ChatBackend(Protocol):
    def stream(self, messages: list[Message]) -> AsyncIterator[str]: ...


def mock_reply(messages: list[Message]) -> str:
    """Deterministic: same history in, same text out."""
    last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    turns = sum(1 for m in messages if m.role == "user")
    return (
        f"You said: {last_user!r}. "
        f"This is turn {turns} of a mock chat served by FastAPI. "
        "Tokens arrive one by one over Server-Sent Events."
    )


class MockBackend:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        # "word + trailing whitespace" ~ a token; joining them restores the text.
        for token in re.findall(r"\S+\s*", mock_reply(messages)):
            await asyncio.sleep(self.delay)  # cancellation point
            yield token


class OpenAICompatBackend:
    """Any OpenAI-compatible `/chat/completions` endpoint (OpenAI, vLLM, Ollama...)."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.s = settings
        self.transport = transport  # lets tests inject httpx.MockTransport

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        body = {
            "model": self.s.openai_model,
            "stream": True,
            "messages": [m.model_dump() for m in messages],
        }
        headers = {"Authorization": f"Bearer {self.s.openai_api_key}"}
        async with httpx.AsyncClient(transport=self.transport, timeout=60.0) as http:
            async with http.stream(
                "POST", f"{self.s.openai_base_url}/chat/completions", json=body, headers=headers
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line.removeprefix("data: ")
                    if payload == "[DONE]":
                        return
                    delta = json.loads(payload)["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta


def get_backend(settings: Annotated[Settings, Depends(get_settings)]) -> ChatBackend:
    """Dependency: route handlers ask for a backend, never build one."""
    if settings.backend == "openai":
        return OpenAICompatBackend(settings)
    return MockBackend(settings.token_delay)


# ------------------------------------------------------------------ stats ---
@dataclass
class Stats:
    started: int = 0
    completed: int = 0
    cancelled: int = 0
    failed: int = 0
    active: int = field(default=0)


STATS = Stats()


def get_stats() -> Stats:
    return STATS


# -------------------------------------------------------------------- app ---
app = FastAPI(title="AEFS FastAPI chat lab", version="0.1.0")

Backend = Annotated[ChatBackend, Depends(get_backend)]
StatsDep = Annotated[Stats, Depends(get_stats)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@app.get("/api/health")
async def health(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "backend": settings.backend}


@app.get("/api/stats")
async def stats(s: StatsDep) -> Stats:
    return s


@app.post("/api/chat")
async def chat(req: ChatRequest, backend: Backend) -> ChatResponse:
    parts = [t async for t in backend.stream(req.messages)]
    return ChatResponse(reply="".join(parts), tokens=len(parts))


@app.post("/api/chat/stream", response_class=EventSourceResponse)
async def chat_stream(req: ChatRequest, backend: Backend, s: StatsDep) -> AsyncIterator[ServerSentEvent]:
    """`yield` + `EventSourceResponse` → FastAPI frames each item as an SSE event."""
    s.started += 1
    s.active += 1
    n = 0
    try:
        async for token in backend.stream(req.messages):
            n += 1
            yield ServerSentEvent(event="token", data={"text": token})
        yield ServerSentEvent(event="done", data={"tokens": n})
        s.completed += 1
    except asyncio.CancelledError:
        # The browser closed the connection (Stop button / tab closed).
        # Starlette cancels this generator; count it, then re-raise.
        s.cancelled += 1
        raise
    except Exception as exc:  # noqa: BLE001 — headers are already sent: report in-band
        s.failed += 1
        yield ServerSentEvent(event="error", data={"message": f"{type(exc).__name__}: {exc}"})
    finally:
        s.active -= 1


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
