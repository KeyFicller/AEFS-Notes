"""Minimal plan / act / observe loop.

Bounded agent scaffold:
1. bounded context (budget)
2. structured plan state
3. sandboxed tool dispatcher
4. hook callbacks

搜「重构：」可以跳到每一处改动。注释写的是「为什么这样改」和「以后怎么接」，
不是复述代码在做什么。
"""

import os
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

# 重构：删掉了没用到的 runpy.run_path。
# 没人调用的 import 会让读代码的人去找一条不存在的执行路径。
# 标准库 import 放一起，按模块名排序。


# ------------------------------------------
# Plan
# ------------------------------------------

class TodoStatus(str, Enum):
    """任务状态。

    重构：原稿用散落的字符串（"pending"、"in_progress"……）。
    拼错要到渲染时才 KeyError。str Enum 在构造时就拒绝非法值，
    打印、比较时仍然是普通字符串。
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"

    @property
    def mark(self) -> str:
        # 重构：原稿 pending 和 in_progress 都画 🔄，清单上看不出谁还没开始。
        return {
            TodoStatus.PENDING: "⬜",
            TodoStatus.IN_PROGRESS: "🔄",
            TodoStatus.DONE: "✅",
            TodoStatus.FAILED: "❌",
        }[self]


@dataclass
class TodoItem:
    id: int
    description: str
    status: TodoStatus
    # 留给这一步的失败原因或观察。整表替换 plan 时要带上，否则会丢。见 agent_loop。
    note: str = ""


@dataclass
class PlanState:
    goal: str
    items: list[TodoItem] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Goal: {self.goal}"]
        for item in self.items:
            lines.append(f"{item.status.mark} {item.description}")
        return "\n".join(lines)


# ------------------------------------------
# Budget
# ------------------------------------------

@dataclass
class UsageStats:
    turns: int = 0
    tokens: int = 0
    # 重构：金额用 float 只能演示。0.1 + 0.2 不等于 0.3。
    # 以后若真扣费，改成「毫分」的 int，或 decimal.Decimal。
    money: float = 0.0


@dataclass
class Budget:
    max: UsageStats = field(default_factory=lambda: UsageStats(10, 200_000, 5.00))
    used: UsageStats = field(default_factory=UsageStats)

    def step(self, tokens: int, money: float) -> None:
        self.used.turns += 1
        self.used.tokens += tokens
        self.used.money += money

    def exceeded(self) -> str | None:
        # 重构：原稿用 `>`。max.turns = 10 时，第 11 轮开始前 used 已经是 10，
        # `10 > 10` 为假，循环还会再跑一轮，实际上限是 11。
        # 到顶就停，用 >=。若以后想「超限后只收尾、不再调工具」，在 agent_loop 里分支，
        # 不要把这里改回 >。
        checks = (
            ("turns", self.used.turns, self.max.turns),
            ("tokens", self.used.tokens, self.max.tokens),
            ("money", self.used.money, self.max.money),
        )
        for name, used, limit in checks:
            if used >= limit:
                return f"{name} budget reached: used {used} of {limit}."
        return None


# ------------------------------------------
# Hooks
# ------------------------------------------

HookFn = Callable[[dict[str, Any]], dict[str, Any] | None]


class HookBus:
    # 重构：原稿是 set。set 无序，而且类属性可变，
    # 任何人都能 HookBus.EVENTS.add(...) 改掉事件表。tuple 两者都避免。
    EVENTS: tuple[str, ...] = (
        "Session_Start",
        "Session_End",
        "Pre_Tool_Use",
        "Post_Tool_Use",
        "User_Prompt_Submit",
        "Notification",
        "Stop",
        "Pre_Compact",
    )

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookFn]] = {event: [] for event in self.EVENTS}

    def _bucket(self, event: str) -> list[HookFn]:
        try:
            return self._hooks[event]
        except KeyError:
            known = ", ".join(self.EVENTS)
            raise ValueError(f"unknown hook {event!r}; expected one of: {known}") from None

    def on(self, event: str, fn: HookFn) -> None:
        # 重构：原稿直接 KeyError，报错里看不到合法事件名。
        self._bucket(event).append(fn)

    def emit(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """按注册顺序调用 hook。

        重构：原稿写 `payload = fn(payload) or payload`。
        空字典在布尔语境里是 False，一次想「换成空 payload」的 hook 会被丢掉，
        调用方继续拿旧数据。None 才表示「不替换」：就地修改过的那个 dict 仍然有效。
        """
        for fn in self._bucket(event):
            updated = fn(payload)
            if updated is not None:
                payload = updated
        return payload


class Trace:
    """把 hook 收到的 payload 按时间记下来。

    重构：原稿用 `(trace.append({...}), payload)[1]`。
    append 返回 None，靠元组下标把 payload 传回去，读的人要在脑子里先执行一遍。
    旁路记录就显式 return 原 payload。
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, event: str) -> HookFn:
        def hook(payload: dict[str, Any]) -> dict[str, Any]:
            self.events.append({"event": event, **payload})
            return payload

        return hook


# ------------------------------------------
# Tools
# ------------------------------------------

TRUNCATE_BYTES = 4096


def resolve_in_sandbox(sandbox: str, path: str) -> str:
    """把相对路径解析成沙箱内的真实路径，逃出沙箱就拒绝。

    重构：原稿用 realpath(full).startswith(realpath(sandbox))。
    沙箱若是 /tmp/box，../box_evil/x 的真实路径是 /tmp/box_evil/x，
    它以 /tmp/box 开头，校验会放行。commonpath 比的是路径分量。
    """
    root = os.path.realpath(sandbox)
    full = os.path.realpath(os.path.join(root, path))
    if os.path.commonpath([root, full]) != root:
        raise RuntimeError(f"path escapes sandbox: {path}")
    return full


def clip(text: str, limit: int = TRUNCATE_BYTES) -> str:
    """按字节截断，并标明后面还有内容。

    重构：原稿 `text[:4096]` 截的是字符，常量名却叫 BYTES；而且静默截断，
    调用方分不清「文件就这么短」和「被砍了」。
    """
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    kept = data[:limit].decode("utf-8", errors="ignore")
    return f"{kept}\n...[truncated, {len(data) - limit} bytes omitted]"


def tool_read_file(sandbox: str, path: str) -> str:
    full = resolve_in_sandbox(sandbox, path)
    with open(full, encoding="utf-8", errors="replace") as handle:
        return clip(handle.read())


def tool_run_shell(sandbox: str, command: str, timeout: int = 30) -> str:
    """在沙箱目录下执行一条命令。

    重构：原稿 shell=True，整行字符串交给 shell 再解释一次。
    `ls && rm -rf /` 这种链接、重定向、命令替换都会生效。
    模型侧仍传字符串（它习惯吐一行命令）；真正执行时用 shlex 拆成 argv，shell=False。

    cwd 只能决定相对路径从哪开始。进程仍可读写绝对路径，这不是沙箱。
    以后要隔离，用容器或单独的系统用户，不要在命令字符串上打补丁。
    """
    argv = shlex.split(command)
    if not argv:
        raise RuntimeError("empty command")
    proc = subprocess.run(
        argv,
        cwd=sandbox,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = clip(proc.stdout + proc.stderr)
    return f"exit = {proc.returncode}\n{out}"


TOOLS: dict[str, Callable[..., str]] = {
    "read_file": tool_read_file,
    "run_shell": tool_run_shell,
}


def dispatch_tool(name: str, sandbox: str, args: dict[str, Any]) -> str:
    # 重构：直接 TOOLS[name] 会抛 KeyError，看起来像解释器崩了。
    # 未知工具是这一步没做成，转成 RuntimeError，让循环记一笔失败再继续。
    try:
        fn = TOOLS[name]
    except KeyError:
        raise RuntimeError(f"unknown tool: {name}") from None
    return fn(sandbox, **args)


# ------------------------------------------
# Scripted model
# ------------------------------------------

@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class ModelStep:
    """一轮「模型」的输出。

    重构：原稿返回 dict，键是 "plan" / "tool" / "tokens" / "cost"。
    拼错键要到取值时才炸，类型检查也帮不上。字段写在 dataclass 上，
    缺什么、类型是什么，定义处就能看见。
    原稿模型侧叫 cost、预算侧叫 money，这里统一用 money。
    """

    plan: list[TodoItem]
    tool: ToolCall | None
    tokens: int
    money: float


@dataclass
class ScriptBeat:
    """写死的一拍。接入真模型后删掉这张表，不要让模型去填它。"""

    plan: tuple[tuple[str, TodoStatus], ...]
    tool: ToolCall | None
    tokens: int
    money: float


SCRIPT: tuple[ScriptBeat, ...] = (
    ScriptBeat(
        plan=(
            ("locate target file", TodoStatus.IN_PROGRESS),
            ("read target file", TodoStatus.PENDING),
            ("apply fix and verify", TodoStatus.PENDING),
        ),
        tool=ToolCall("run_shell", {"command": "ls"}),
        tokens=1200,
        money=0.02,
    ),
    ScriptBeat(
        plan=(
            ("locate target file", TodoStatus.DONE),
            ("read target file", TodoStatus.IN_PROGRESS),
            ("apply fix and verify", TodoStatus.PENDING),
        ),
        tool=ToolCall("read_file", {"path": "test_file.txt"}),
        tokens=1200,
        money=0.02,
    ),
    ScriptBeat(
        plan=(
            ("locate target file", TodoStatus.DONE),
            ("read target file", TodoStatus.DONE),
            ("apply fix and verify", TodoStatus.DONE),
        ),
        tool=None,
        tokens=1200,
        money=0.02,
    ),
)


def model_step(plan: PlanState, turn: int) -> ModelStep:
    """用剧本假装模型。

    重构：真循环里，上一步工具的输出就是下一步的观察。
    这个函数不接收 observation，SCRIPT 也不会读它，所以 observe 目前只出现在 trace 里。
    接入模型时改成 model_step(plan, turn, observation)，不要继续把工具返回值丢掉。
    """
    if turn >= len(SCRIPT):
        return ModelStep(plan=list(plan.items), tool=None, tokens=2000, money=0.01)

    beat = SCRIPT[turn]
    items = [
        TodoItem(index + 1, description, status)
        for index, (description, status) in enumerate(beat.plan)
    ]
    return ModelStep(plan=items, tool=beat.tool, tokens=beat.tokens, money=beat.money)


# ------------------------------------------
# Guard
# ------------------------------------------

def destructive_guard(payload: dict[str, Any]) -> dict[str, Any]:
    """演示用的拒绝名单。

    重构：原稿 `if "rm -rf" in command` 挡不住 `RM -RF`、`rm -fr`、`rm -r -f`，
    也挡不住先写进变量再执行。这里只把大小写和连续空格收一收。
    这不是安全边界。shell=False 也挡不住 argv 形式的 `rm -rf /`。
    """
    command = " ".join(payload.get("args", {}).get("command", "").lower().split())
    denied = ("rm -rf", "rm -fr", "shutdown", "mkfs")
    if any(needle in command for needle in denied):
        payload["blocked"] = True
        payload["reason"] = "Destructive command blocked"
    return payload


# ------------------------------------------
# Agent loop
# ------------------------------------------

@dataclass
class AgentResult:
    plan: str
    budget: UsageStats
    trace: list[dict[str, Any]]
    # 重构：结束原因是结果的一等字段。原因见 main() 里那条注释。
    stop_reason: str


def agent_loop(task: str, sandbox: str) -> AgentResult:
    plan = PlanState(task)
    budget = Budget()
    hooks = HookBus()
    trace = Trace()

    hooks.on("Pre_Tool_Use", destructive_guard)
    hooks.on("Post_Tool_Use", trace.record("tool"))
    hooks.on("Session_Start", trace.record("start"))
    hooks.on("Session_End", trace.record("end"))
    # 重构：原稿 emit 了 Stop，但没有 hook 记录它。结束原因因此丢失。
    hooks.on("Stop", trace.record("stop"))

    hooks.emit("Session_Start", {
        "task": task,
        "sandbox": sandbox,
        "started_at": time.time(),
    })

    turn = 0
    stop_reason = "complete"
    while True:
        reason = budget.exceeded()
        if reason:
            stop_reason = reason
            hooks.emit("Stop", {"reason": stop_reason, "turn": turn})
            break

        step = model_step(plan, turn)
        # 重构：剧本每一拍都交回整张清单，id 从 1 重排，TodoItem.note 也会被清掉。
        # 真模型应返回对上一版 plan 的增量；在那之前，替换时要把还需要的 note 合并回来。
        plan.items = step.plan
        budget.step(step.tokens, step.money)
        # 重构：原稿在工具执行末尾才 turn += 1，最后一轮没有工具，
        # Stop 里的 turn 和 budget.turns 会差 1。轮次只在这里加一次。
        turn += 1

        call = step.tool
        if call is None:
            stop_reason = "complete"
            hooks.emit("Stop", {"reason": stop_reason, "turn": turn})
            break

        pre = hooks.emit("Pre_Tool_Use", {"tool": call.name, "args": call.args})
        if pre.get("blocked"):
            # 重构：原稿拦截后仍 emit Post_Tool_Use，但 payload 里没有 ok / reason，
            # trace 看起来像一次普通调用。拦截是失败，要写明。
            hooks.emit("Post_Tool_Use", {
                "tool": call.name,
                "ok": False,
                "blocked": True,
                "reason": pre.get("reason", ""),
            })
            continue

        try:
            result = dispatch_tool(call.name, sandbox, call.args)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            # 重构：原稿 except Exception 会把 TypeError（参数传错）也当成工具失败吞掉，
            # bug 看起来像「模型又没做成」。这里只接住「这一步没做成」的错误。
            hooks.emit("Post_Tool_Use", {
                "tool": call.name,
                "ok": False,
                "error": str(exc),
            })
            continue

        hooks.emit("Post_Tool_Use", {
            "tool": call.name,
            "ok": True,
            "bytes": len(result),
        })

    hooks.emit("Session_End", {
        "turns": budget.used.turns,
        "tokens": budget.used.tokens,
        "money": budget.used.money,
        "ended_at": time.time(),
    })
    return AgentResult(
        plan=plan.summary(),
        budget=budget.used,
        trace=trace.events,
        stop_reason=stop_reason,
    )


def main() -> None:
    task = "demonstrate the plan-act-observe loop without network calls"
    sandbox = os.path.dirname(os.path.abspath(__file__))
    result = agent_loop(task, sandbox)

    print(result.plan)
    print("-" * 80)
    print(asdict(result.budget))
    print("-" * 80)
    for event in result.trace:
        print(
            event["event"],
            event.get("tool", ""),
            event.get("ok", ""),
            event.get("bytes", 0),
        )
    print("-" * 80)
    # 重构：原稿打印 trace[-1].get("reason")。
    # Session_End 记在 Stop 之后，最后一条是 end，没有 reason，那一行永远是空的。
    print(result.stop_reason)


if __name__ == "__main__":
    main()
