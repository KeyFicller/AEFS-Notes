from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NATIVE = ROOT / "native"
BINARY = ROOT / "DeskPet"


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
    cmd = ["swiftc", "-O", "-o", str(BINARY), "-framework", "AppKit", *[str(p) for p in files]]
    subprocess.check_call(cmd)


def main() -> None:
    if needs_compile():
        compile_native()
    raise SystemExit(subprocess.call([str(BINARY)]))


if __name__ == "__main__":
    main()
