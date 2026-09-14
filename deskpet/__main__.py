from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NATIVE = ROOT / "native"
BINARY = ROOT / "DeskPet"
PUBLIC_URL = ROOT / "inbox" / "public-url.txt"
NGROK_API = "http://127.0.0.1:4040/api/tunnels"


def sources() -> list[Path]:
    return sorted(NATIVE.glob("*.swift"))


def needs_compile() -> bool:
    files = sources()
    if not files or not BINARY.exists():
        return True
    binary_mtime = BINARY.stat().st_mtime
    return any(src.stat().st_mtime > binary_mtime for src in files)


def compile_native() -> None:
    files = sources()
    if not files:
        sys.exit("DeskPet: no Swift sources in deskpet/native")
    cmd = [
        "swiftc",
        "-O",
        "-o",
        str(BINARY),
        "-framework",
        "AppKit",
        "-framework",
        "Network",
        *[str(p) for p in files],
    ]
    subprocess.check_call(cmd)


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text())


def save_config(cfg: dict) -> None:
    (ROOT / "config.json").write_text(
        json.dumps(cfg, indent=2, sort_keys=True) + "\n"
    )


def wait_for_port(port: int, timeout: float = 12) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def write_public_url(base: str) -> None:
    PUBLIC_URL.parent.mkdir(parents=True, exist_ok=True)
    url = base.rstrip("/")
    if not url.endswith("/inbox"):
        url = url + "/inbox"
    PUBLIC_URL.write_text(url + "\n")
    print(f"DeskPet: inbox public {url}", file=sys.stderr)


def remember_hostname(host: str) -> None:
    host = host.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
    if not host:
        return
    cfg = load_config()
    if cfg.get("inbox_hostname") == host:
        return
    cfg["inbox_hostname"] = host
    save_config(cfg)


def drain(proc: subprocess.Popen) -> None:
    if proc.stdout is None:
        return
    for _ in proc.stdout:
        pass


def stop_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def ngrok_bin() -> str | None:
    return shutil.which("ngrok")


def start_ngrok(port: int, hostname: str) -> subprocess.Popen | None:
    exe = ngrok_bin()
    if not exe:
        print(
            "DeskPet: ngrok not found. Install with `brew install ngrok`, "
            "then `ngrok config add-authtoken <token>`.",
            file=sys.stderr,
        )
        return None
    cmd = [exe, "http", str(port), "--log=stdout"]
    if hostname:
        cmd.extend(["--url", f"https://{hostname}"])
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def ngrok_public_url() -> str | None:
    try:
        with urllib.request.urlopen(NGROK_API, timeout=1) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    for tunnel in payload.get("tunnels") or []:
        url = str(tunnel.get("public_url") or "")
        if url.startswith("https://"):
            return url.rstrip("/")
    return None


def wait_ngrok_url(proc: subprocess.Popen, timeout: float = 25) -> str | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            rest = proc.stdout.read() if proc.stdout else ""
            if rest:
                print(rest, end="", file=sys.stderr)
            print(
                "DeskPet: ngrok exited. Sign up at https://dashboard.ngrok.com/signup "
                "and run `ngrok config add-authtoken <token>`.",
                file=sys.stderr,
            )
            return None
        url = ngrok_public_url()
        if url:
            return url
        time.sleep(0.25)
    return None


def start_inbox_tunnel(cfg: dict, port: int) -> subprocess.Popen | None:
    hostname = str(cfg.get("inbox_hostname") or "").strip()
    proc = start_ngrok(port, hostname)
    if proc is None:
        return None
    threading.Thread(target=drain, args=(proc,), daemon=True).start()
    public = wait_ngrok_url(proc)
    if not public:
        print("DeskPet: ngrok did not publish a URL", file=sys.stderr)
        return proc
    write_public_url(public)
    remember_hostname(public)
    return proc


def main() -> None:
    if needs_compile():
        compile_native()
    cfg = load_config()
    port = int(cfg.get("inbox_port", 8765))
    tunnel_on = bool(cfg.get("inbox_tunnel", True))
    pet = subprocess.Popen([str(BINARY)])
    tunnel: subprocess.Popen | None = None
    try:
        if tunnel_on and port > 0:
            if not wait_for_port(port):
                print("DeskPet: inbox port not open; skip tunnel", file=sys.stderr)
            else:
                tunnel = start_inbox_tunnel(cfg, port)
        raise SystemExit(pet.wait())
    finally:
        stop_proc(tunnel)
        PUBLIC_URL.unlink(missing_ok=True)
        if pet.poll() is None:
            stop_proc(pet)


if __name__ == "__main__":
    main()
