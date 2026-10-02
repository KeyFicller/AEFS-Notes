import sys
import shutil
import subprocess

CHECKS = [
    ("Python 3.10+", lambda: sys.version_info >= (3, 10), f"Python {sys.version}"),
    ("NumPy", lambda: __import__("numpy"), None),
    ("Matplotlib", lambda: __import__("matplotlib"), None),
    ("Jupyter", lambda: __import__("jupyter"), None),
    ("Git", lambda: shutil.which("git") is not None, None),
    ("Node.js", lambda: shutil.which("node") is not None, None),
    ("Rust (cargo)", lambda: shutil.which("cargo") is not None, None),
]

GPU_CEHCKS = [
    ("Pytorch", lambda: __import__("torch"), None),
    (
        "Cuda",
        lambda: __import__("torch").cuda.is_available(), 
        lambda: __import__("torch").cuda.get_device_name(0) if __import__("torch").cuda.is_available() else "Not avaliable"
    ),
]

def run_check(name, check_fn, detail_fn=None):
    try:
        result = check_fn()
        if result is False:
            raise Exception(f"Check returned False")
        detail = ""
        if detail_fn:
            if callable(detail_fn):
                detail = f"({detail_fn()})"
            else:
                detail = f"({detail_fn})"
        print(f"  [PASS] {name} {detail}")
        return True
    except Exception:
        print(f"  [FAIL] {name}")
        return False

def main():
    print("Checking development environment...")
    print("--------------------------------")

    passed = sum(run_check(name, check_fn, detail_fn) for name, check_fn, detail_fn in CHECKS)
    passed += sum(run_check(name, check_fn, detail_fn) for name, check_fn, detail_fn in GPU_CEHCKS)

    print("--------------------------------")
    print(f"Environment check result: {passed}/{len(CHECKS) + len(GPU_CEHCKS)}")
    print("--------------------------------")

    if passed != len(CHECKS) + len(GPU_CEHCKS):
        print("Some checks failed. Please check the output above.")
        return 1
    else:
        print("All checks passed!")
        return 0

if __name__ == "__main__":
    main()