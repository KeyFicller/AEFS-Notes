# 01 · FastAPI chat + SSE + static frontend

Stage 1 of the `codes/fastapi/` track: a small **FastAPI** service that streams a
chat reply token by token, plus a **single static HTML page** (no build step)
that calls it. The LLM path reuses the repo's **LangGraph** stack
(`StateGraph` / `MessagesState` / `astream(..., stream_mode="messages")`), the
same shape as `codes/langgraph/01_state_graph` + `05_streaming`.

Default offline model is LangChain's **`FakeListChatModel`** (deterministic, no
API key). With `DEEPSEEK_API_KEY` (or `CHAT_MODEL=deepseek`) it switches to
`init_chat_model("deepseek:…")` like the LangGraph notebooks.

## Run

```bash
# from repo root (once)
pip install -r codes/requirements.txt

cd codes/fastapi/01_chat_sse_frontend
python app.py                  # http://127.0.0.1:8000  ← open in a browser
                               # http://127.0.0.1:8000/docs  ← Swagger from the Pydantic models

# smoke test over real HTTP (starts and stops its own server)
python client.py --spawn
```

## What each piece teaches

| Piece | Where | Lesson |
| --- | --- | --- |
| Route + Pydantic body | `ChatRequest` / `ChatResponse` | invalid bodies become `422` with a `loc` path; no hand-written `if` |
| `Depends` | `get_settings` → `get_graph` | handlers ask for a compiled graph; tests swap it via `app.dependency_overrides` |
| LangGraph LLM | `build_chat_graph` + `stream_tokens` | one-node `MessagesState` graph; tokens from `astream(..., stream_mode="messages")` |
| `async def` endpoint | `/api/chat`, `/api/chat/stream` | `await` points are where cancellation lands |
| SSE | `EventSourceResponse` + `yield ServerSentEvent(...)` | `event: token` / `event: done` frames; errors after the headers go in-band as `event: error` |
| Disconnect | `except asyncio.CancelledError` in the stream generator | Stop button → `AbortController.abort()` → server generator cancelled (`/api/stats`) |
| Frontend | `static/index.html` | `fetch` POST + `ReadableStream` + a ~25-line SSE parser |

## Swap in a real LLM

Default is offline `FakeListChatModel`. For a live DeepSeek model (same wiring as
`codes/langgraph/`):

```bash
# put the key in codes/langgraph/local.env (already loaded) or export it
export DEEPSEEK_API_KEY=sk-...
# optional: CHAT_MODEL=deepseek DEEPSEEK_MODEL=deepseek-v4-flash
python app.py
```

Or force the fake path even when a key is present: `CHAT_MODEL=fake python app.py`.

## Design choices

- **LangGraph, not hand-rolled backends.** Token streaming is
  `graph.astream(..., stream_mode="messages")` — the same API the LangGraph
  track teaches. FastAPI only owns routes, Depends, SSE, and the static page.
- **SSE, not WebSocket.** Token streaming is one-way server → client, SSE is plain
  HTTP (works with `curl`, proxies, `fetch`), and a closed connection is the
  cancel signal. WebSocket earns its place when the client must send *while* the
  server streams (voice, collaborative editing); that is a candidate for stage 2.
- **`POST` + `fetch`, not `EventSource`.** The browser's `EventSource` only does
  `GET`, so it cannot carry the chat history. The page parses the frames itself.
- **Stateless server.** The browser re-sends the whole `messages` list each turn.
  No sessions, no database (LangGraph checkpointers are a later topic).
- **`fastapi.sse` is new.** `EventSourceResponse` / `ServerSentEvent` need
  `fastapi>=0.135` (pinned in the shared requirements). Before that you wrote
  `StreamingResponse` plus a `f"event: ...\ndata: ...\n\n"` helper. Exercise 3 in
  `qa.ipynb` prints the raw frames so the wire is still visible.

## Layout

- `app.py` — schemas, `Settings`, LangGraph graph factory, `Depends`, routes, `main()`
- `static/index.html` — the chat page (HTML + CSS + JS in one file)
- `client.py` — smoke test: health, page served, OpenAPI, 422, one-shot vs SSE
  parity, incremental delivery, disconnect cancellation
- `qa.ipynb` — 9 short exercises, executed, outputs committed
- deps live in the shared `codes/requirements.txt` (no second requirements tree)

## Skipped on purpose

WebSocket, auth / API keys on the route, rate limiting, CORS (page and API share an
origin), server-side sessions / LangGraph checkpointers, Markdown rendering in the
page, retries / `Last-Event-ID` resume, background tasks, `lifespan` resources,
deployment (uvicorn workers, reverse proxy buffering), and tests under pytest.
Calling a blocking function from `async def` (the classic FastAPI foot-gun) is
described in `codes/summary/fastapi.html` but not exercised here.
