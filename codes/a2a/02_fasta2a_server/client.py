"""Drive FastA2A AgentCard → message/send → input-required → completed.

Uses fasta2a's A2AClient (httpx under the hood). Contrasts with stage-1:
method names are `message/send` / `tasks/get`, roles are `user`/`agent`,
task states are kebab-case, JSON-RPC lands on `/`, and each send creates
a *new* task (continue the conversation with the same `context_id`).

Usage (server must already be running, or use --spawn):

    python client.py
    python client.py --spawn
    python client.py --base-url http://127.0.0.1:41243
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fasta2a.client import A2AClient
from fasta2a.schema import Message, Part

DEFAULT_BASE = "http://127.0.0.1:41243"
TERMINAL_OR_WAIT = (
    "input-required",
    "completed",
    "failed",
    "canceled",
    "rejected",
    "auth-required",
)


def new_user_message(
    parts: list[Part],
    *,
    context_id: str | None = None,
    task_id: str | None = None,
) -> Message:
    message: Message = {
        "role": "user",
        "parts": parts,
        "message_id": str(uuid.uuid4()),
    }
    if context_id:
        message["context_id"] = context_id
    if task_id:
        message["task_id"] = task_id
    return message


async def wait_for_server(base_url: str, attempts: int = 50) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    last_err: Exception | None = None
    for _ in range(attempts):
        try:
            response = httpx.get(url, timeout=1.0)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 — lab wait loop
            last_err = exc
            await asyncio.sleep(0.1)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_err}")


async def poll_task(
    client: A2AClient,
    task_id: str,
    *,
    want: tuple[str, ...] = TERMINAL_OR_WAIT,
    attempts: int = 40,
) -> dict[str, Any]:
    """FastA2A returns the Task immediately in `submitted`; poll `tasks/get`."""
    for i in range(attempts):
        response = await client.get_task(task_id)
        if "error" in response:
            raise RuntimeError(f"tasks/get error: {response['error']}")
        task = response["result"]
        state = task["status"]["state"]
        if state in want:
            return task
        await asyncio.sleep(0.05)
    raise RuntimeError(f"task {task_id} did not leave submitted/working in time")


def _task_from_send(response: dict[str, Any]) -> dict[str, Any]:
    if "error" in response:
        raise RuntimeError(f"message/send error: {response['error']}")
    result = response["result"]
    # FastA2A wraps as {"task": {...}}; tolerate a bare Task too.
    if isinstance(result, dict) and "task" in result:
        return result["task"]
    return result


async def demo(base_url: str) -> None:
    print("=" * 64)
    print("A2A stage-2 · FastA2A Worker + message/send")
    print("=" * 64)

    print("\n--- 1. discover AgentCard ---")
    card = await wait_for_server(base_url)
    print(f"name          → {card.get('name')}")
    print(f"skills        → {[s.get('id') for s in card.get('skills', [])]}")
    interfaces = card.get("supportedInterfaces") or card.get("supported_interfaces") or []
    for iface in interfaces:
        binding = iface.get("protocolBinding") or iface.get("protocol_binding")
        version = iface.get("protocolVersion") or iface.get("protocol_version")
        print(f"interface     → {binding} {version} @ {iface.get('url')}")

    async with httpx.AsyncClient(timeout=10.0) as http:
        # Pass agent=base_url — A2AClient overwrites http_client.base_url from agent.
        client = A2AClient(agent=base_url, http_client=http)

        print("\n--- 2. message/send (no targetLength → input-required) ---")
        first = new_user_message([Part(text="Summarize the attached source about MCP vs A2A.")])
        resp1 = await client.send_message(first)
        task1 = _task_from_send(resp1)
        print(f"task id       → {task1['id']}  (state on return: {task1['status']['state']})")
        print(f"context id    → {task1['context_id']}")
        task1 = await poll_task(client, task1["id"])
        print(f"state         → {task1['status']['state']}")
        ask = None
        for msg in reversed(task1.get("history") or []):
            if msg.get("role") == "agent":
                parts = msg.get("parts") or []
                if parts and parts[0].get("text"):
                    ask = parts[0]["text"]
                    break
        print(f"agent asks    → {ask}")
        context_id = task1["context_id"]

        print("\n--- 3. message/send follow-up (same context_id, new task) ---")
        follow = new_user_message(
            [Part(data={"targetLength": "3 paragraphs"}, media_type="application/json")],
            context_id=context_id,
        )
        resp2 = await client.send_message(follow)
        task2 = _task_from_send(resp2)
        print(f"task id       → {task2['id']}  (same as first? {task2['id'] == task1['id']})")
        task2 = await poll_task(client, task2["id"])
        print(f"state         → {task2['status']['state']}")
        artifacts = task2.get("artifacts") or []
        if artifacts:
            art = artifacts[0]
            print(f"artifact      → {art.get('name')}")
            print(f"content       → {(art.get('parts') or [{}])[0].get('text')}")

        print("\n--- 4. stage-1 vs stage-2 (one-liner) ---")
        print(
            "Stage-1 (stdlib): visible A2A 1.0.1 wire — SendMessage, TASK_STATE_*, "
            "ROLE_*, /a2a/jsonrpc, A2A-Version, same taskId for follow-up. "
            "Stage-2 (FastA2A): framework owns the wire — message/send, kebab states, "
            "user/agent roles, POST /, new task per send + context_id continuity."
        )


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
        parsed = urlparse(args.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 41243
        proc = subprocess.Popen(
            [sys.executable, str(server), "--host", host, "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            asyncio.run(demo(args.base_url))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    else:
        asyncio.run(demo(args.base_url))


if __name__ == "__main__":
    main()
