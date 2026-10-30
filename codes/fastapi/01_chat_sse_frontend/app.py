"""Stage-1 FastAPI lab: routes + Pydantic + Depends + async SSE + static frontend.

The LLM path is the same LangGraph stack as `codes/langgraph/`: a one-node
`StateGraph(MessagesState)` streamed with `astream(..., stream_mode="messages")`.
Default offline model is LangChain's `FakeListChatModel` (no API key). With
`DEEPSEEK_API_KEY` (or `CHAT_MODEL=deepseek`) it switches to
`init_chat_model("deepseek:…")` like the LangGraph notebooks.

Run:

    python app.py                    # http://127.0.0.1:8000  (open in a browser)
    python app.py --port 8000

Endpoints:
  GET  /                       the static chat page (static/index.html)
  GET  /api/health             liveness + which model is wired
  GET  /api/stats              stream counters (started / completed / cancelled)
  POST /api/chat               one-shot JSON reply
  POST /api/chat/stream        Server-Sent Events: `token` ... `done` (or `error`)
  GET  /docs                   Swagger UI generated from the Pydantic models
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# Same canned reply FakeListChatModel cycles through (deterministic, offline).
FAKE_REPLY = (
    "You said hello to FastAPI + LangGraph. "
    "This is a deterministic FakeListChatModel reply. "
    "Tokens arrive one by one over Server-Sent Events."
)


def _load_env_file(path: Path) -> None:
    """Write KEY=VALUE lines into os.environ (existing keys win)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


# Match codes/langgraph: optional local.env next to that track.
_load_env_file(HERE.parents[1] / "langgraph" / "local.env")
_load_env_file(HERE / "local.env")


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
    model_mode: Literal["fake", "deepseek"] = "fake"
    token_delay: float = 0.02  # seconds between FakeListChatModel chars
    deepseek_model: str = "deepseek-v4-flash"


@lru_cache
def get_settings() -> Settings:
    """Read env once. Tests swap it with `app.dependency_overrides`."""
    explicit = os.getenv("CHAT_MODEL", "").strip().lower()
    if explicit in ("fake", "deepseek"):
        mode: Literal["fake", "deepseek"] = explicit  # type: ignore[assignment]
    else:
        mode = "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "fake"
    return Settings(
        model_mode=mode,
        token_delay=float(os.getenv("FAKE_TOKEN_DELAY", os.getenv("MOCK_TOKEN_DELAY", "0.02"))),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    )


# ---------------------------------------------------------- LangGraph LLM ---
def build_model(settings: Settings) -> BaseChatModel:
    """Offline: FakeListChatModel. Live: init_chat_model + DEEPSEEK_*."""
    if settings.model_mode == "deepseek":
        from langchain.chat_models import init_chat_model

        return init_chat_model(f"deepseek:{settings.deepseek_model}")
    return FakeListChatModel(responses=[FAKE_REPLY], sleep=settings.token_delay)


def build_chat_graph(model: BaseChatModel):
    """One-node MessagesState graph — same shape as codes/langgraph/01_state_graph."""

    def agent(state: MessagesState) -> dict:
        return {"messages": [model.invoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()


def get_graph(settings: Annotated[Settings, Depends(get_settings)]):
    """Dependency: handlers ask for a compiled graph, never build one inline."""
    return build_chat_graph(build_model(settings))


_ROLE_TO_LC: dict[str, type[BaseMessage]] = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def to_lc_messages(messages: list[Message]) -> list[BaseMessage]:
    return [_ROLE_TO_LC[m.role](content=m.content) for m in messages]


def _chunk_text(content: Any) -> str:
    """Normalize AIMessageChunk.content (str, or rare multimodal list) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content is not None else ""


async def stream_tokens(graph, messages: list[Message]) -> AsyncIterator[str]:
    """Token stream via LangGraph `astream(..., stream_mode="messages")`."""
    async for chunk, _meta in graph.astream(
        {"messages": to_lc_messages(messages)},
        stream_mode="messages",
    ):
        text = _chunk_text(getattr(chunk, "content", ""))
        if text:
            yield text


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
app = FastAPI(title="AEFS FastAPI chat lab", version="0.2.0")

GraphDep = Annotated[Any, Depends(get_graph)]
StatsDep = Annotated[Stats, Depends(get_stats)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@app.get("/api/health")
async def health(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "model": settings.model_mode}


@app.get("/api/stats")
async def stats(s: StatsDep) -> Stats:
    return s


@app.post("/api/chat")
async def chat(req: ChatRequest, graph: GraphDep) -> ChatResponse:
    parts = [t async for t in stream_tokens(graph, req.messages)]
    return ChatResponse(reply="".join(parts), tokens=len(parts))


@app.post("/api/chat/stream", response_class=EventSourceResponse)
async def chat_stream(req: ChatRequest, graph: GraphDep, s: StatsDep) -> AsyncIterator[ServerSentEvent]:
    """`yield` + `EventSourceResponse` → FastAPI frames each item as an SSE event."""
    s.started += 1
    s.active += 1
    n = 0
    try:
        async for token in stream_tokens(graph, req.messages):
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
