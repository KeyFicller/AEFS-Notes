# 01 · AgentCard + JSON-RPC SendMessage

Stage 1 of the `codes/a2a/` track. Teaches the **A2A 1.0.1 wire** that the
upstream [A2A 101 capture kit](https://github.com/rohitg00/ai-engineering-from-scratch/tree/main/manuals/a2a-101/capture)
records: discover an Agent Card, send `SendMessage` over JSON-RPC with the
`A2A-Version` header, and watch a task move
`SUBMITTED/WORKING → INPUT_REQUIRED → COMPLETED`.

## Why stdlib (not the official SDK)

MCP stage 1 uses **FastMCP** because the lesson is "write typed tools; let the
framework own the protocol." A2A stage 1 is the opposite lesson: **see the
card path, the JSON-RPC envelope, PascalCase methods, and `TASK_STATE_*`
names**. The capture kit is dependency-free Python for the same reason. An
`a2a-sdk` lab can come later once the wire is familiar.

No new entry in `codes/requirements.txt` — this stage needs only the stdlib.

## Run

```bash
# terminal A
cd codes/a2a/01_agentcard_sendmessage
python server.py                 # http://127.0.0.1:41242

# terminal B
python client.py
# or one-shot:
python client.py --spawn
```

Notebook (starts the server in a background thread):

```bash
jupyter notebook qa.ipynb
# or: jupyter nbconvert --to notebook --execute qa.ipynb --inplace
```

## What you should see

1. `GET /.well-known/agent-card.json` → `writer-agent` with a JSONRPC interface
2. First `SendMessage` without `targetLength` → `TASK_STATE_INPUT_REQUIRED`
3. Follow-up `SendMessage` on the same `taskId` / `contextId` →
   `TASK_STATE_COMPLETED` + a summary artifact
4. A request missing `A2A-Version` → JSON-RPC error `-32009`

## MCP vs A2A (keep this contrast)

| | MCP | A2A |
|---|---|---|
| Who talks | Host ↔ tool server (one agent’s tools) | Agent ↔ agent |
| Discovery | `tools/list` / resources / prompts | Agent Card at `/.well-known/agent-card.json` |
| Unit of work | tool call | **task** with lifecycle states |
| Typical method | `tools/call` | `SendMessage` / `SendStreamingMessage` |

## Skipped on purpose (honest scope)

| Topic | Why skipped in stage 1 |
|---|---|
| `SendStreamingMessage` / SSE frames | Separate stage; needs event-stream handling |
| HTTP+JSON (`/a2a/rest`) and gRPC bindings | Same operations, different naming; JSON-RPC is enough to learn the model |
| `ListTasks`, `CancelTask`, push notifications | Optional capabilities; card flags them off here |
| `TASK_STATE_AUTH_REQUIRED` / bearer auth | Needs an out-of-band approval path |
| Official `a2a-sdk` | Would hide the wire this lab is meant to show |
| Spec edge cases (signed cards, extended cards, resubscribe) | Capture kit scenarios 14–18 — later stages |

Wire names follow A2A **1.0.1** (`SendMessage`, `TASK_STATE_*`, `ROLE_USER` /
`ROLE_AGENT`, `A2A-Version: 1.0`). Pre-1.0 names like `message/send` or
`working` are rejected by a 1.0 peer (`-32601`).

## Files

- `server.py` — Agent Card + JSON-RPC dispatcher
- `client.py` — discover → send → follow-up → version-guard demo
- `qa.ipynb` — same path for the learner
- `README.md` — this file
