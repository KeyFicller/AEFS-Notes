# 07_list_changed

Stage 7 of `codes/mcp/`: **list_changed + resource updated** notifications
on FastMCP + Pydantic (`2026-07-28`).

## Why this stage (skipped alternatives)

Checked against FastMCP **4.1.x** before writing the lab:

| Candidate | Status on `2026-07-28` | Why skipped |
| --- | --- | --- |
| Sampling (`Context.sample`) | Missing on `Context` | No server→client sampling back-channel in FastMCP 4.1 |
| Roots (`session.list_roots`) | Deprecated (SEP-2577) + needs back-channel | Not teachable without lying about current protocol |
| Imperative elicitation (`ctx.elicit`) | Raises era-aware `ToolError` | Back-channel removed (SEP-2322 / SEP-2575) |
| Protocol logging (`ctx.info` / `notifications/message`) | Deprecated (SEP-2577) | Stage 3 already redirects to progress / stderr |
| `resources/subscribe` | Removed | Spec replacement is `subscriptions/listen`; FastMCP `Client` does not expose `.listen()` yet |

This stage teaches what *is* client-visible today: install a
`MessageHandler`, react to `tools/list_changed` (from
`ctx.enable_components`) and `resources/updated` (explicit
`ctx.send_notification`), then **refetch**.

## Files

- `server.py` — `lab://board` resource, `post_board`, `unlock_secret`, hidden `secret_ping`
- `client.py` — `MessageHandler` demo / unlock / post CLI
- `qa.ipynb` — short exercises

## Run

```bash
pip install -r ../../requirements.txt
python client.py
python client.py unlock
python client.py post --text hello
```
