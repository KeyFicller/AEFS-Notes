"""Spawn the lab tools server and drive initialize → tools/list → tools/call.

Usage:

    python client.py
    python client.py add --a 2 --b 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SERVER = Path(__file__).resolve().with_name("server.py")


class StdioClient:
    def __init__(self, server_path: Path = SERVER) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 1

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("server stdio is not available")
        message = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        }
        self._next_id += 1
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()
        raw = self._proc.stdout.readline()
        if not raw:
            err = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"server closed stdout; stderr={err!r}")
        return json.loads(raw)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._proc.stdin is None:
            raise RuntimeError("server stdin is not available")
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()


def demo(tool: str, arguments: dict[str, Any]) -> None:
    client = StdioClient()
    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lab-tools-client", "version": "0.1.0"},
            },
        )
        print("initialize →", json.dumps(init["result"], ensure_ascii=False))
        client.notify("notifications/initialized")

        listed = client.request("tools/list")
        names = [t["name"] for t in listed["result"]["tools"]]
        print("tools/list →", names)

        called = client.request("tools/call", {"name": tool, "arguments": arguments})
        print("tools/call →", json.dumps(called["result"], ensure_ascii=False))
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", default="echo")
    parser.add_argument("--text", default="hello MCP")
    parser.add_argument("--a", type=float, default=2.0)
    parser.add_argument("--b", type=float, default=3.0)
    args = parser.parse_args()

    if args.tool == "echo":
        demo("echo", {"text": args.text})
    elif args.tool == "add":
        demo("add", {"a": args.a, "b": args.b})
    else:
        demo(args.tool, {})


if __name__ == "__main__":
    main()
