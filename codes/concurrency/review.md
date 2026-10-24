# 并发入门 · 两分钟复盘

忘了就从这里背。细节回 `guide.html` / `qa.ipynb`，结论用 `python check.py` 量。

## 选型三问

1. 只有一两件事？→ **串行**。
2. 瓶颈在**算**（纯 Python / 重循环）？→ **进程**（`ProcessPoolExecutor`）。线程帮不上忙。
3. 瓶颈在**等**（网络、磁盘、数据库）？
   - 路数不多 → **线程池**
   - 路数很多 → **asyncio + Semaphore**

| 瓶颈 | 用什么 | 别用什么 |
| --- | --- | --- |
| CPU | 进程 / 子解释器 | 线程 |
| I/O | 线程或协程 | 为加速而开进程（太贵） |

## 五条必须记住

1. **GIL**：同一时刻只有一个线程在跑 Python 字节码。等 I/O 时会放开。
2. **竞态**：共享变量的读-改-写中间一旦让出，无锁必丢。解法：`threading.Lock`，或干脆别共享。
3. **限流**：`asyncio.Semaphore(N)`，别一次 `gather` 打爆下游。
4. **失败 / 超时**：`gather(..., return_exceptions=True)` 收住单个失败；`wait_for` / `timeout` 卡死任务。
5. **阻塞毁掉协程**：协程里调 `time.sleep` / 同步 `requests` = 整条事件循环卡住。要么 `await`，要么 `asyncio.to_thread`。

## 完成顺序

- `as_completed`：谁先好先处理（推流、边收边写）。
- `gather`：按输入顺序收齐。

## 笔记本两个坑

- 单元格里别 `asyncio.run`（事件循环已在跑）→ 直接 `await`。
- 交给进程池的函数必须在**模块级**（用 `bench.py`），单元格里 `def` 子进程看不到。

## 自测口令（入门默写）

不看答案先答：

1. 4 次纯 Python 计算，线程池会比串行快吗？
2. 8 次 `sleep(0.2)`，线程池约多快？
3. 无锁自增 8000 次，实得会怎样？加锁呢？
4. 9 个 0.2s 请求、`Semaphore(3)`，总耗时约多少？
5. 协程里 `time.sleep(0.2)` × 5，约多少秒？

答案：1 不会（≈一样）· 2 ≈8 倍 · 3 远小于 8000 / 等于 8000 · 4 ≈0.6s（三批）· 5 ≈1.0s（没有并发）。

---

# 并发进阶 · 再两分钟

入门会 `gather` / `Semaphore` / `wait_for` 之后，再背这三件：`TaskGroup`、取消、`Queue`。

## TaskGroup vs gather

| | `asyncio.gather` | `asyncio.TaskGroup` |
| --- | --- | --- |
| 一个失败 | 默认立刻抛；**兄弟还在跑** | 取消兄弟，退出时抛 `ExceptionGroup` |
| 适用 | 「尽量收齐 / 部分成功」 | 「这批活必须同生共死」 |
| 版本 | 老写法 | 3.11+ |

```python
async with asyncio.TaskGroup() as tg:
    tg.create_task(fetch(a))
    tg.create_task(fetch(b))
# 任一失败 → 其余被取消 → except* 接 ExceptionGroup
```

要「一个挂了别人继续」：继续用 `gather(..., return_exceptions=True)`。

## 取消三步

1. `task.cancel()`：下次 `await` 点注入 `CancelledError`。
2. 协程里通常 **再 raise**（或 `raise` 原异常），别默默吞掉——吞了等于撒谎说「我正常结束」。
3. `asyncio.shield(coro)`：外层 `wait_for` / `cancel` 取消的是**等待者**，被 shield 的活继续跑。只在「超时也要落盘 / 提交」时用；别到处 shield。

`wait_for` 超时本身就会取消目标；和 `TaskGroup` 的「取消兄弟」是同一套取消机制。

## Queue 背压

```python
q = asyncio.Queue(maxsize=2)  # 满了，put 就 await
await q.put(item)             # 生产者被下游速度卡住 = 背压
item = await q.get()
```

- `maxsize` 限制在途消息，防止生产者把内存打爆。
- 结束约定：放一个哨兵（如 `None`），或单独的 `Event` / `task_done` 计数。
- Semaphore 限的是**并发任务数**；Queue 限的是**在途数据量**。常一起用。

## 进阶自测口令

1. `TaskGroup` 里一个任务抛错，兄弟任务会怎样？抛出的是什么？
2. `gather` 默认失败时，兄弟还会跑完吗？
3. `task.cancel()` 之后，协程在什么时候真正收到 `CancelledError`？
4. `shield` + `wait_for` 超时：被保护的任务还会跑完吗？
5. `Queue(maxsize=2)`，慢消费者时，第 3 次 `put` 会怎样？

答案：1 被取消 + `ExceptionGroup` · 2 会 · 3 下一次 `await` · 4 会 · 5 阻塞等待直到有空位。
