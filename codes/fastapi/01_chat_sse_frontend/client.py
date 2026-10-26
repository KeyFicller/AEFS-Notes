"""Smoke test for app.py over real HTTP (httpx). Exits non-zero on failure.

    python client.py --spawn          # start app.py, run checks, stop it
    python client.py                  # server already running on :8000
    python client.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
DEFAULT_BASE = "http://127.0.0.1:8000"
CHAT = {"messages": [{"role": "user", "content": "hello fastapi"}]}


def wait_for_server(base: str, attempts: int = 50) -> dict:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            r = httpx.get(f"{base}/api/health", timeout=1.0)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 — lab wait loop
            last = exc
            time.sleep(0.1)
    raise RuntimeError(f"server not ready at {base}: {last}")


def sse_frames(resp: httpx.Response) -> Iterator[tuple[str, dict]]:
    """Parse `event:` / `data:` frames from a streaming response."""
    event, data = "message", []
    for line in resp.iter_lines():
        if line == "":
            if data:
                yield event, json.loads("".join(data))
            event, data = "message", []
        elif line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data.append(line.removeprefix("data: "))


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        raise SystemExit(1)


def run(base: str) -> None:
    with httpx.Client(base_url=base, timeout=30.0) as http:
        h = http.get("/api/health").json()
        check("health", h["status"] == "ok" and h.get("model") in ("fake", "deepseek"),
              f"model={h.get('model')}")

        page = http.get("/")
        check("GET / serves the static page", page.status_code == 200 and "text/html" in page.headers["content-type"]
              and "/api/chat/stream" in page.text)
        check("GET /static/index.html", http.get("/static/index.html").status_code == 200)
        check("OpenAPI generated", "/api/chat/stream" in http.get("/openapi.json").json()["paths"])

        bad = http.post("/api/chat", json={"messages": [{"role": "user", "content": ""}]})
        check("Pydantic validation → 422", bad.status_code == 422, bad.json()["detail"][0]["loc"].__repr__())

        one = http.post("/api/chat", json=CHAT).json()
        check("POST /api/chat", one["tokens"] > 5, one["reply"][:40] + "…")

        tokens, done, stamps = [], None, []
        t0 = time.perf_counter()
        with http.stream("POST", "/api/chat/stream", json=CHAT) as resp:
            check("stream content-type", resp.headers["content-type"].startswith("text/event-stream"))
            for event, data in sse_frames(resp):
                stamps.append(time.perf_counter() - t0)
                if event == "token":
                    tokens.append(data["text"])
                elif event == "done":
                    done = data
        check("SSE tokens join to the one-shot reply", "".join(tokens) == one["reply"])
        check("SSE done event", done == {"tokens": len(tokens)})
        # streaming, not buffered: the first frame must land well before the last one
        check("frames arrive incrementally", stamps[0] < stamps[-2] / 2, f"first={stamps[0]:.2f}s last={stamps[-2]:.2f}s")

        before = http.get("/api/stats").json()
        with http.stream("POST", "/api/chat/stream", json=CHAT) as resp:
            for i, (event, _) in enumerate(sse_frames(resp)):
                if i == 2:
                    break  # leave the `with` → connection closed mid-stream
        for _ in range(40):
            after = http.get("/api/stats").json()
            if after["cancelled"] > before["cancelled"]:
                break
            time.sleep(0.1)
        check("client disconnect cancels the generator", after["cancelled"] == before["cancelled"] + 1
              and after["active"] == 0, json.dumps(after))
    print("all checks passed")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default=DEFAULT_BASE)
    p.add_argument("--spawn", action="store_true", help="start app.py for the duration of the run")
    args = p.parse_args()
    proc = None
    if args.spawn:
        port = httpx.URL(args.base_url).port
        proc = subprocess.Popen(
            [sys.executable, str(HERE / "app.py"), "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    try:
        wait_for_server(args.base_url)
        run(args.base_url)
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
