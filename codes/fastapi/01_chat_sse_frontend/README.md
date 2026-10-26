# 01 · FastAPI chat + SSE + static frontend

Stage 1 of the `codes/fastapi/` track: a small **FastAPI** service that streams a
chat reply token by token, plus a **single static HTML page** (no build step)
that calls it. It pairs with the repo's async/agent tracks: the generator you
`yield` from is the same `async for` / `CancelledError` machinery as
`codes/concurrency/`, and the streaming UI is what an agent front end looks like.

The "LLM" is a **deterministic mock** (words + `asyncio.sleep`), so it runs with
no API key and gives the same text every time.

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
| `Depends` | `get_settings` → `get_backend` | handlers ask for a backend; tests swap it via `app.dependency_overrides` |
| `async def` endpoint | `/api/chat`, `/api/chat/stream` | `await` points are where cancellation lands |
| SSE | `EventSourceResponse` + `yield ServerSentEvent(...)` | `event: token` / `event: done` frames; errors after the headers go in-band as `event: error` |
| Disconnect | `except asyncio.CancelledError` in the stream generator | Stop button → `AbortController.abort()` → server generator cancelled (`/api/stats`) |
| Frontend | `static/index.html` | `fetch` POST + `ReadableStream` + a ~25-line SSE parser |

## Swap in a real LLM

`ChatBackend` is a one-method protocol (`stream(messages) -> AsyncIterator[str]`).
`OpenAICompatBackend` implements it over any OpenAI-compatible
`/chat/completions` endpoint (OpenAI, vLLM, Ollama, ...):

```bash
CHAT_BACKEND=openai OPENAI_API_KEY=sk-... OPENAI_MODEL=gpt-4o-mini python app.py
# local server: OPENAI_BASE_URL=http://localhost:11434/v1
```

Honest status: this class is verified **offline only** (exercise 8 in `qa.ipynb`
feeds it a fake SSE reply through `httpx.MockTransport`). It was not run against
a live provider here.

## Design choices

- **SSE, not WebSocket.** Token streaming is one-way server → client, SSE is plain
  HTTP (works with `curl`, proxies, `fetch`), and a closed connection is the
  cancel signal. WebSocket earns its place when the client must send *while* the
  server streams (voice, collaborative editing); that is a candidate for stage 2.
- **`POST` + `fetch`, not `EventSource`.** The browser's `EventSource` only does
  `GET`, so it cannot carry the chat history. The page parses the frames itself.
- **Stateless server.** The browser re-sends the whole `messages` list each turn.
  No sessions, no database.
- **`fastapi.sse` is new.** `EventSourceResponse` / `ServerSentEvent` need
  `fastapi>=0.135` (pinned in the shared requirements). Before that you wrote
  `StreamingResponse` plus a `f"event: ...\ndata: ...\n\n"` helper. Exercise 3 in
  `qa.ipynb` prints the raw frames so the wire is still visible.

## Layout

- `app.py` — schemas, `Settings`, backends, `Depends`, routes, `main()`
- `static/index.html` — the chat page (HTML + CSS + JS in one file)
- `client.py` — smoke test: health, page served, OpenAPI, 422, one-shot vs SSE
  parity, incremental delivery, disconnect cancellation
- `qa.ipynb` — 9 short exercises, executed, outputs committed
- deps live in the shared `codes/requirements.txt` (no second requirements tree)

## Skipped on purpose

WebSocket, auth / API keys on the route, rate limiting, CORS (page and API share an
origin), server-side sessions or persistence, Markdown rendering in the page,
retries / `Last-Event-ID` resume, background tasks, `lifespan` resources,
deployment (uvicorn workers, reverse proxy buffering), and tests under pytest.
Calling a blocking function from `async def` (the classic FastAPI foot-gun) is
described in `codes/summary/fastapi.html` but not exercised here.
