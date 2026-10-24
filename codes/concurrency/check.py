#!/usr/bin/env python3
"""并发专题的自检：把 qa.ipynb 里的结论逐条量一遍。

入门层：CPU/I/O 选型、竞态+锁、限流、失败/超时、
as_completed 顺序、同步阻塞毁掉并发。

进阶层：TaskGroup 结构化并发、取消 / shield、Queue 背压。

耗时断言给的是宽区间，机器忙的时候也不会误报；真正防的是「结论写反了」。
全部通过约 12 秒。
"""

from __future__ import annotations

import asyncio
import sys
import threading
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


def race_and_lock() -> None:
    """读-改-写中间让出一次，无锁必丢；加锁后等于期望。"""

    def bump_unlocked(counter: list[int], n: int) -> None:
        for _ in range(n):
            current = counter[0]
            time.sleep(0)  # yield so another thread can interleave
            counter[0] = current + 1

    unlocked = [0]
    threads = [
        threading.Thread(target=bump_unlocked, args=(unlocked, 2000))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check(
        "无锁竞态会丢计数",
        unlocked[0] < 8000,
        f"期望 8000，实得 {unlocked[0]}",
    )

    lock = threading.Lock()

    def bump_locked(counter: list[int], n: int) -> None:
        for _ in range(n):
            with lock:
                counter[0] += 1

    locked = [0]
    threads = [
        threading.Thread(target=bump_locked, args=(locked, 2000))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("加锁后计数正确", locked[0] == 8000, f"期望 8000，实得 {locked[0]}")


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


def as_completed_order() -> None:
    async def finish(name: str, delay: float) -> str:
        await asyncio.sleep(delay)
        return name

    async def collect() -> list[str]:
        coros = [finish("a", 0.3), finish("b", 0.1), finish("c", 0.2)]
        out: list[str] = []
        for fut in asyncio.as_completed(coros):
            out.append(await fut)
        return out

    order = asyncio.run(collect())
    check(
        "as_completed 按完成顺序",
        order[0] == "b" and set(order) == {"a", "b", "c"},
        f"得到 {order}，最快的 b 应先回来",
    )


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



def taskgroup_vs_gather() -> None:
    """TaskGroup 失败会取消兄弟并抛 ExceptionGroup；gather 默认不取消兄弟。"""

    async def tg_case() -> tuple[bool, int]:
        late = False

        async def slow() -> None:
            nonlocal late
            try:
                await asyncio.sleep(1.0)
                late = True
            except asyncio.CancelledError:
                raise

        async def boom() -> None:
            await asyncio.sleep(0.05)
            raise ValueError("tg boom")

        n_exc = 0
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(slow())
                tg.create_task(boom())
        except* ValueError as eg:
            n_exc = len(eg.exceptions)
        return late, n_exc

    late, n_exc = asyncio.run(tg_case())
    check("TaskGroup 失败会取消兄弟任务", late is False, f"慢任务是否跑完 late={late}")
    check("TaskGroup 抛 ExceptionGroup", n_exc == 1, f"ValueError 个数 {n_exc}")

    async def gather_case() -> bool:
        late = False

        async def slow() -> str:
            nonlocal late
            await asyncio.sleep(0.2)
            late = True
            return "ok"

        async def boom() -> None:
            await asyncio.sleep(0.05)
            raise ValueError("gather boom")

        try:
            await asyncio.gather(slow(), boom())
        except ValueError:
            pass
        await asyncio.sleep(0.25)
        return late

    late_g = asyncio.run(gather_case())
    check("gather 默认不取消兄弟任务", late_g is True, f"慢任务是否跑完 late={late_g}")


def cancellation_and_shield() -> None:
    async def cancel_one() -> bool:
        started = asyncio.Event()
        saw = False

        async def long() -> None:
            nonlocal saw
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                saw = True
                raise

        t = asyncio.create_task(long())
        await started.wait()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        return saw and t.cancelled()

    check(
        "task.cancel 触发 CancelledError",
        asyncio.run(cancel_one()),
        "长任务应被取消且 cancelled() 为 True",
    )

    async def shielded() -> bool:
        finished = asyncio.Event()

        async def work() -> str:
            await asyncio.sleep(0.15)
            finished.set()
            return "done"

        try:
            await asyncio.wait_for(asyncio.shield(work()), timeout=0.05)
        except TimeoutError:
            pass
        await asyncio.sleep(0.2)
        return finished.is_set()

    check(
        "shield 保住被保护的任务",
        asyncio.run(shielded()),
        "0.05s 超时后，被 shield 的 0.15s 任务仍应跑完",
    )


def queue_backpressure() -> None:
    async def run() -> tuple[list[int], list[int]]:
        q: asyncio.Queue[int | None] = asyncio.Queue(maxsize=2)
        blocked: list[int] = []

        async def producer() -> None:
            for i in range(5):
                t0 = time.perf_counter()
                await q.put(i)
                if time.perf_counter() - t0 > 0.02:
                    blocked.append(i)
            await q.put(None)

        async def consumer() -> list[int]:
            out: list[int] = []
            await asyncio.sleep(0.05)  # let producer fill to maxsize
            while True:
                item = await q.get()
                if item is None:
                    break
                out.append(item)
                await asyncio.sleep(0.08)
            return out

        cons = asyncio.create_task(consumer())
        prod = asyncio.create_task(producer())
        out = await cons
        await prod
        return out, blocked

    elapsed, (out, blocked) = timed(lambda: asyncio.run(run()))
    check("Queue 按顺序交付", out == [0, 1, 2, 3, 4], f"得到 {out}")
    check(
        "Queue(maxsize) 会背压生产者",
        len(blocked) >= 1,
        f"被挡住的 put 序号 {blocked}，总耗时 {elapsed:.2f}s",
    )



def main() -> int:
    cpu_and_io()
    race_and_lock()
    semaphore_cap()
    as_completed_order()
    failure_handling()
    blocking_in_async()
    taskgroup_vs_gather()
    cancellation_and_shield()
    queue_backpressure()
    if failures:
        print(f"\n{len(failures)} 项失败: {', '.join(failures)}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
