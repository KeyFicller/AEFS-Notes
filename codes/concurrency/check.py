#!/usr/bin/env python3
"""并发专题的自检：把 qa.ipynb 里的结论逐条量一遍。

耗时断言给的是宽区间，机器忙的时候也不会误报；真正防的是「结论写反了」。
全部通过约 8 秒。
"""

from __future__ import annotations

import asyncio
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bench  # noqa: E402

N = bench.N


def timed(fn) -> tuple[float, object]:
    start = time.perf_counter()
    value = fn()
    return time.perf_counter() - start, value


def best(fn, times: int = 2) -> tuple[float, object]:
    """跑几次取最快的一次，减少系统抖动。"""
    runs = [timed(fn) for _ in range(times)]
    return min(runs, key=lambda r: r[0])


failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")
    if not ok:
        failures.append(name)


def cpu_and_io() -> None:
    serial, _ = best(lambda: [bench.cpu_work(N) for _ in range(4)], 1)
    with ThreadPoolExecutor(4) as ex:
        threads, _ = best(lambda: list(ex.map(bench.cpu_work, [N] * 4)))
    with ProcessPoolExecutor(4) as ex:
        procs, _ = best(lambda: list(ex.map(bench.cpu_work, [N] * 4)))

    check("CPU 密集：线程帮不上忙", threads > serial * 0.7,
          f"串行 {serial:.2f}s，线程 {threads:.2f}s")
    check("CPU 密集：进程明显更快", procs < serial * 0.8,
          f"串行 {serial:.2f}s，进程 {procs:.2f}s")

    serial_io, _ = best(lambda: [bench.io_work(0.2) for _ in range(8)], 1)
    with ThreadPoolExecutor(8) as ex:
        threads_io, _ = best(lambda: list(ex.map(bench.io_work, [0.2] * 8)))
    check("I/O 密集：线程快一个数量级", threads_io < serial_io * 0.35,
          f"串行 {serial_io:.2f}s，线程 {threads_io:.2f}s")


def semaphore_cap() -> None:
    async def run() -> list[int]:
        sem = asyncio.Semaphore(3)
        peak = 0
        live = 0

        async def one(i: int) -> int:
            nonlocal peak, live
            async with sem:
                live += 1
                peak = max(peak, live)
                await asyncio.sleep(0.2)
                live -= 1
            return i

        out = await asyncio.gather(*[one(i) for i in range(9)])
        return [len(out), peak]

    elapsed, (count, peak) = timed(lambda: asyncio.run(run()))
    check("Semaphore 真的限住并发", peak <= 3, f"峰值并发 {peak}")
    check("限流总耗时约等于三批", 0.55 <= elapsed <= 1.2,
          f"9 个 0.2s 请求、上限 3 个，用时 {elapsed:.2f}s，收了 {count} 个")


def failure_handling() -> None:
    async def boom(i: int) -> int:
        if i == 2:
            raise RuntimeError(f"req {i} failed")
        return i

    async def collect() -> list[object]:
        return await asyncio.gather(*[boom(i) for i in range(5)], return_exceptions=True)

    results = asyncio.run(collect())
    errors = [r for r in results if isinstance(r, Exception)]
    check("return_exceptions 收住单个失败", len(results) == 5 and len(errors) == 1,
          f"5 个结果里有 {len(errors)} 个异常")

    async def slow() -> None:
        await asyncio.sleep(1)

    try:
        asyncio.run(asyncio.wait_for(slow(), timeout=0.2))
    except TimeoutError:
        check("wait_for 会超时", True, "等 0.2s 就放弃 1s 的任务")
    else:
        check("wait_for 会超时", False, "1 秒的任务居然没超时")


def blocking_in_async() -> None:
    async def blocking() -> None:
        async def one() -> None:
            time.sleep(0.2)

        await asyncio.gather(*[one() for _ in range(5)])

    async def yielding() -> None:
        async def one() -> None:
            await asyncio.sleep(0.2)

        await asyncio.gather(*[one() for _ in range(5)])

    bad, _ = timed(lambda: asyncio.run(blocking()))
    good, _ = timed(lambda: asyncio.run(yielding()))
    check("同步阻塞会毁掉并发", bad > 0.9, f"5 个 0.2s：time.sleep {bad:.2f}s")
    check("await 让出控制权", good < 0.4, f"5 个 0.2s：asyncio.sleep {good:.2f}s")


def main() -> int:
    cpu_and_io()
    semaphore_cap()
    failure_handling()
    blocking_in_async()
    if failures:
        print(f"\n{len(failures)} 项失败: {', '.join(failures)}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
