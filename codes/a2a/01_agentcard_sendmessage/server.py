"""Stage-1 A2A server: AgentCard discovery + JSON-RPC SendMessage.

Stdlib only — mirrors the A2A 101 capture-kit style so the wire protocol
(card path, A2A-Version header, PascalCase methods, TASK_STATE_*) stays
visible. This is a teaching subset, not the official a2a-sdk.

Run:

    python server.py                 # http://127.0.0.1:41242
    python server.py --port 41242

Endpoints:
  GET  /.well-known/agent-card.json
  POST /a2a/jsonrpc   (SendMessage; optional GetTask)
"""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

A2A_VERSION = "1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 41242

AGENT_CARD: dict[str, Any] = {
    "name": "writer-agent",
    "description": "Drafts a short technical summary from source text.",
    "version": "1.0.0",
    "supportedInterfaces": [
        {
            "url": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/a2a/jsonrpc",
            "protocolBinding": "JSONRPC",
            "protocolVersion": A2A_VERSION,
        }
    ],
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["text/markdown"],
    "skills": [
        {
            "id": "draft_summary",
            "name": "Draft summary",
            "description": "Given source text and a targetLength, produce a short summary.",
            "tags": ["writing", "summarization"],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["text/markdown"],
        }
    ],
}

TASK_STORE: dict[str, dict[str, Any]] = {}
_STORE_LOCK = threading.Lock()


def _part_field(part: dict[str, Any]) -> str | None:
    """A Part holds exactly one of text / raw / url / data (A2A 1.0.1)."""
    present = [name for name in ("text", "raw", "url", "data") if name in part]
    if len(present) != 1:
        return None
    return present[0]


def _new_agent_message(text: str, task_id: str, context_id: str) -> dict[str, Any]:
    return {
        "messageId": str(uuid.uuid4()),
        "taskId": task_id,
        "contextId": context_id,
        "role": "ROLE_AGENT",
        "parts": [{"text": text}],
    }


def _extract_target_length(parts: list[dict[str, Any]]) -> str | None:
    for part in parts:
        if _part_field(part) == "data" and isinstance(part.get("data"), dict):
            value = part["data"].get("targetLength")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _finish(task: dict[str, Any], length: str) -> None:
    text = (
        f"[writer-agent] {length} summary of provided source: "
        "topic identified, key points extracted, conclusion drafted."
    )
    task["artifacts"].append(
        {
            "artifactId": str(uuid.uuid4()),
            "name": "summary",
            "parts": [{"text": text, "mediaType": "text/markdown"}],
        }
    )
    done = _new_agent_message("Summary ready.", task["id"], task["contextId"])
    task["status"] = {"state": "TASK_STATE_COMPLETED", "message": done}
    task["history"].append(done)


def handle_send_message(params: dict[str, Any]) -> dict[str, Any]:
    message = params.get("message")
    if not isinstance(message, dict):
        raise ValueError("params.message is required")
    if not message.get("messageId"):
        raise ValueError("message.messageId is required")
    if message.get("role") != "ROLE_USER":
        raise ValueError("client messages must use role ROLE_USER")
    parts = message.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("message.parts must be a non-empty list")
    for part in parts:
        if not isinstance(part, dict) or _part_field(part) is None:
            raise ValueError("each Part holds exactly one of text, raw, url, data")

    task_id = message.get("taskId")
    with _STORE_LOCK:
        if task_id:
            task = TASK_STORE.get(task_id)
            if task is None:
                raise LookupError(task_id)
            if task["status"]["state"] in {
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_CANCELED",
                "TASK_STATE_REJECTED",
            }:
                raise RuntimeError("task is terminal")
            # Resume after INPUT_REQUIRED: stamp WORKING, then finish or re-ask.
            task["status"] = {"state": "TASK_STATE_WORKING"}
            task["history"].append(message)
            length = _extract_target_length(parts)
            if length is None:
                ask = _new_agent_message(
                    "Please specify targetLength as a data part "
                    '(e.g. {"data": {"targetLength": "3 paragraphs"}}).',
                    task["id"],
                    task["contextId"],
                )
                task["status"] = {
                    "state": "TASK_STATE_INPUT_REQUIRED",
                    "message": ask,
                }
                task["history"].append(ask)
            else:
                _finish(task, length)
            return {"task": task}

        task = {
            "id": f"task_{uuid.uuid4().hex[:10]}",
            "contextId": str(uuid.uuid4()),
            "status": {"state": "TASK_STATE_SUBMITTED"},
            "artifacts": [],
            "history": [],
        }
        TASK_STORE[task["id"]] = task
        # Stamp context/task ids onto the stored user message for history readers.
        stored = dict(message)
        stored["taskId"] = task["id"]
        stored["contextId"] = task["contextId"]
        task["history"].append(stored)
        task["status"] = {"state": "TASK_STATE_WORKING"}

        length = _extract_target_length(parts)
        if length is None:
            ask = _new_agent_message(
                "Please specify targetLength as a data part "
                '(e.g. {"data": {"targetLength": "3 paragraphs"}}).',
                task["id"],
                task["contextId"],
            )
            task["status"] = {
                "state": "TASK_STATE_INPUT_REQUIRED",
                "message": ask,
            }
            task["history"].append(ask)
        else:
            _finish(task, length)
        return {"task": task}


def handle_get_task(params: dict[str, Any]) -> dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    if not task_id:
        raise ValueError("params.id (task id) is required")
    with _STORE_LOCK:
        task = TASK_STORE.get(task_id)
        if task is None:
            raise LookupError(task_id)
        return {"task": task}


def dispatch_rpc(headers: dict[str, str], request: dict[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {"jsonrpc": "2.0", "id": request.get("id")}
    version = headers.get("A2A-Version") or headers.get("a2a-version")
    if version != A2A_VERSION:
        response["error"] = {
            "code": -32009,
            "message": "VersionNotSupportedError",
            "data": {"expected": A2A_VERSION, "got": version},
        }
        return response

    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "SendMessage":
            response["result"] = handle_send_message(params)
        elif method == "GetTask":
            response["result"] = handle_get_task(params)
        else:
            response["error"] = {
                "code": -32601,
                "message": "Method not found",
                "data": {"method": method},
            }
    except LookupError as exc:
        response["error"] = {
            "code": -32001,
            "message": "TaskNotFoundError",
            "data": {"taskId": str(exc)},
        }
    except RuntimeError as exc:
        response["error"] = {
            "code": -32004,
            "message": "TaskNotCancelableError",
            "data": {"detail": str(exc)},
        }
    except ValueError as exc:
        response["error"] = {
            "code": -32602,
            "message": "Invalid params",
            "data": {"detail": str(exc)},
        }
    return response


def make_handler(host: str, port: int) -> type[BaseHTTPRequestHandler]:
    card = json.loads(json.dumps(AGENT_CARD))
    card["supportedInterfaces"] = [
        {
            "url": f"http://{host}:{port}/a2a/jsonrpc",
            "protocolBinding": "JSONRPC",
            "protocolVersion": A2A_VERSION,
        }
    ]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Keep lab output readable; client.py prints the lifecycle.
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/.well-known/agent-card.json":
                payload = json.dumps(card, indent=2).encode("utf-8")
                self._send(200, payload, "application/json")
                return
            self._send(404, b'{"error":"not found"}\n', "application/json")

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/a2a/jsonrpc":
                self._send(404, b'{"error":"not found"}\n', "application/json")
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                request = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                body = json.dumps(err).encode("utf-8")
                self._send(200, body, "application/json")
                return
            headers = {k: v for k, v in self.headers.items()}
            reply = dispatch_rpc(headers, request)
            body = json.dumps(reply).encode("utf-8")
            self._send(200, body, "application/json")

    return Handler


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    handler = make_handler(host, port)
    server = ThreadingHTTPServer((host, port), handler)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    server = serve(args.host, args.port)
    print(f"A2A writer-agent listening on http://{args.host}:{args.port}")
    print(f"  card → GET /.well-known/agent-card.json")
    print(f"  rpc  → POST /a2a/jsonrpc  (A2A-Version: {A2A_VERSION})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
