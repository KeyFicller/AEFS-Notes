"""Drive AgentCard discovery → SendMessage → input-required → completed.

Talks HTTP to `server.py` (stdlib urllib). Shows the A2A 1.0.1 JSON-RPC
envelope and the TASK_STATE_* lifecycle without an SDK.

Usage (server must already be running, or use --spawn):

    python client.py
    python client.py --spawn
    python client.py --base-url http://127.0.0.1:41242
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

A2A_VERSION = "1.0"
DEFAULT_BASE = "http://127.0.0.1:41242"


def http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req_headers = dict(headers or {})
    if payload is not None:
        req_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=payload, headers=req_headers, method=method)
    with urlopen(request, timeout=10) as resp:
        raw = resp.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def fetch_card(base_url: str) -> dict[str, Any]:
    return http_json("GET", f"{base_url.rstrip('/')}/.well-known/agent-card.json")


def rpc(
    base_url: str,
    method: str,
    params: dict[str, Any],
    rpc_id: int = 1,
    version: str | None = A2A_VERSION,
) -> dict[str, Any]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if version is not None:
        headers["A2A-Version"] = version
    envelope = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": params,
    }
    return http_json(
        "POST",
        f"{base_url.rstrip('/')}/a2a/jsonrpc",
        body=envelope,
        headers=headers,
    )


def new_user_message(
    parts: list[dict[str, Any]],
    task_id: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": parts,
    }
    if task_id:
        message["taskId"] = task_id
    if context_id:
        message["contextId"] = context_id
    return message


def demo(base_url: str) -> None:
    print("=" * 64)
    print("A2A stage-1 · AgentCard + JSON-RPC SendMessage")
    print("=" * 64)

    print("\n--- 1. discover AgentCard ---")
    card = fetch_card(base_url)
    print(f"name          → {card.get('name')}")
    print(f"skills        → {[s.get('id') for s in card.get('skills', [])]}")
    interfaces = card.get("supportedInterfaces") or []
    for iface in interfaces:
        print(
            f"interface     → {iface.get('protocolBinding')} "
            f"{iface.get('protocolVersion')} @ {iface.get('url')}"
        )

    print("\n--- 2. SendMessage (missing targetLength → INPUT_REQUIRED) ---")
    first = new_user_message(
        [{"text": "Summarize the attached source about MCP vs A2A."}]
    )
    reply = rpc(base_url, "SendMessage", {"message": first}, rpc_id=1)
    if "error" in reply:
        print("error →", json.dumps(reply["error"], indent=2))
        raise SystemExit(1)
    task = reply["result"]["task"]
    state = task["status"]["state"]
    print(f"task id       → {task['id']}")
    print(f"context id    → {task['contextId']}")
    print(f"state         → {state}")
    if state == "TASK_STATE_INPUT_REQUIRED":
        ask = task["status"].get("message", {}).get("parts", [{}])[0].get("text")
        print(f"agent asks    → {ask}")

    print("\n--- 3. SendMessage follow-up on same taskId ---")
    follow = new_user_message(
        [{"data": {"targetLength": "3 paragraphs"}, "mediaType": "application/json"}],
        task_id=task["id"],
        context_id=task["contextId"],
    )
    reply2 = rpc(base_url, "SendMessage", {"message": follow}, rpc_id=2)
    if "error" in reply2:
        print("error →", json.dumps(reply2["error"], indent=2))
        raise SystemExit(1)
    task2 = reply2["result"]["task"]
    print(f"state         → {task2['status']['state']}")
    if task2.get("artifacts"):
        art = task2["artifacts"][0]
        print(f"artifact      → {art.get('name')}")
        print(f"content       → {art['parts'][0].get('text')}")

    print("\n--- 4. MCP vs A2A (one-liner) ---")
    print(
        "MCP = tools/resources for ONE agent (host ↔ server). "
        "A2A = agent-to-agent tasks via AgentCard + SendMessage."
    )

    print("\n--- 5. version header guard (expect -32009) ---")
    bad = rpc(
        base_url,
        "SendMessage",
        {"message": new_user_message([{"text": "ping"}])},
        rpc_id=3,
        version=None,
    )
    err = bad.get("error") or {}
    print(f"missing A2A-Version → code {err.get('code')} ({err.get('message')})")


def wait_for_server(base_url: str, attempts: int = 40) -> None:
    for _ in range(attempts):
        try:
            fetch_card(base_url)
            return
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.05)
    raise RuntimeError(f"server did not become ready at {base_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument(
        "--spawn",
        action="store_true",
        help="Start server.py in a subprocess for this demo, then stop it.",
    )
    args = parser.parse_args()

    proc: subprocess.Popen[bytes] | None = None
    if args.spawn:
        server = Path(__file__).resolve().parent / "server.py"
        # Parse host/port from base URL for the child.
        # Default lab uses 127.0.0.1:41242.
        from urllib.parse import urlparse

        parsed = urlparse(args.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 41242
        proc = subprocess.Popen(
            [sys.executable, str(server), "--host", host, "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_server(args.base_url)
            demo(args.base_url)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    else:
        demo(args.base_url)


if __name__ == "__main__":
    main()
