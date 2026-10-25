# 02 · FastA2A server (framework Worker)

Stage 2 of the `codes/a2a/` track. Stage 1 taught the **visible A2A 1.0.1
wire** with stdlib. This stage flips the lesson the same way MCP stage 1
does: **let the framework own the protocol; you write a Worker**.

Uses [`fasta2a`](https://pypi.org/project/fasta2a/) (Pydantic + Starlette ASGI)
with the in-memory `Storage` / `Broker` and a **framework-agnostic Worker** —
no `fasta2a[pydantic-ai]` / LLM stack. The teaching lab stays deterministic.

## Stage-1 vs stage-2

| Factor | Stage 1 (`01_agentcard_sendmessage`) | Stage 2 (this dir) |
| --- | --- | --- |
| Stack | stdlib `http.server` | FastA2A + uvicorn |
| Lesson | see the wire | hide the wire behind a Worker |
| JSON-RPC URL | `POST /a2a/jsonrpc` | `POST /` |
| Method names | PascalCase `SendMessage`, `GetTask` | `message/send`, `tasks/get` |
| Roles | `ROLE_USER` / `ROLE_AGENT` | `user` / `agent` |
| States | `TASK_STATE_INPUT_REQUIRED`, … | `input-required`, `completed`, … |
| Version header | required `A2A-Version: 1.0` | not enforced by FastA2A |
| Follow-up | same `taskId` continued | **new task** per send; same `context_id` |
| Deps | none (stdlib) | `fasta2a`, `uvicorn`, `httpx` in `codes/requirements.txt` |

FastA2A is opinionated: every `message/send` creates a background Task. The
A2A `context_id` is how a multi-turn conversation shares history across tasks.
That is a real framework choice — document it; don't paper over it by pretending
stage-1's same-task follow-up still applies.

## Why not the Pydantic AI bridge?

`pip install 'fasta2a[pydantic-ai]'` + `agent_to_a2a(...)` is the production
shortcut when you already have a Pydantic AI `Agent`. For this lab we subclass
`Worker` directly so:

1. no API key / model pull into a teaching notebook
2. the Storage → Broker → Worker diagram stays the thing you implement
3. behavior is deterministic (`input-required` then a fixed artifact)

## Run

```bash
# from repo root (once)
pip install -r codes/requirements.txt

# terminal A
cd codes/a2a/02_fasta2a_server
python server.py                 # http://127.0.0.1:41243

# terminal B
python client.py
# or one-shot:
python client.py --spawn
```

Card: `GET /.well-known/agent-card.json`. JSON-RPC: `POST /`.

## Layout

- `server.py` — `SummaryWorker` + `InMemoryStorage` / `InMemoryBroker` + lifespan
- `client.py` — `A2AClient` demo (card → input-required → context follow-up → artifact)
- `qa.ipynb` — short exercises on the same flow
- deps live in the shared `codes/requirements.txt` (no second requirements tree)

## Skipped on purpose

Streaming (`message/stream`), push notifications, custom Storage/Broker backends,
auth-required, the official `a2a-sdk`, and the pydantic-ai bridge. Stage 1 stays
the place to read PascalCase / `TASK_STATE_*` / `A2A-Version` names.
