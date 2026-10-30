# Deep Agents 第 1 阶段：harness 的四根支柱

> 对照 `deepagents 0.7.32` / `langchain 1.4.7` / `langgraph 1.2.18` 核对。离线自检：`python check.py`。

## 1. 为什么需要 "deep" agent

`codes/langgraph/06_prebuilt_react` 里的 ReAct 循环是「模型 ↔ 工具」两节点来回跳。它对 3～5 步的小任务够用，跑长任务会遇到四个问题：

| 问题 | 浅 ReAct 的表现 | deepagents 的对策 |
| --- | --- | --- |
| 上下文爆炸 | 每个工具结果都堆进 `messages`，几十轮后超窗 | 大结果写进**文件系统**，只留路径；超阈值自动**摘要** |
| 目标漂移 | 没有显式计划，做着做着忘了最初要什么 | 可选的 **`write_todos`** 计划工具 |
| 子任务互相污染 | 调研 A 的中间过程挤占做 B 的上下文 | **`task` 子代理**：独立上下文，只回传结论 |
| 每次重造轮子 | 每个项目手写同一套工具和提示 | **harness**：一行 `create_deep_agent` 装好整套 |

这套思路来自 Claude Code、Manus、Deep Research 这类长程代理的共同结构。`deepagents` 把它抽成库。

## 2. 它到底是什么

一句话：`create_deep_agent(...)` = `langchain.agents.create_agent(...)` + 一组预装中间件，返回的仍是 LangGraph 的 `CompiledStateGraph`。所以第 7、10 阶段学过的 `invoke` / `stream` / `checkpointer` / `thread_id` / `interrupt` 全部照用。

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="deepseek:deepseek-v4-flash",   # 也可传 BaseChatModel；不传会退回 claude-sonnet-4-6 并告警
    tools=[web_search],                    # 你自己的业务工具
    system_prompt="你是研究助理。先查资料，再写报告到 /report.md。",
)
out = agent.invoke({"messages": [{"role": "user", "content": "调研 A2A 协议"}]})
out["files"]["/report.md"]["content"]
```

主代理默认中间件栈（`graph.py` 里按此顺序拼装，越靠前越在外层）：

| 顺序 | 中间件 | 提供什么 |
| --- | --- | --- |
| 1 | `FilesystemMiddleware` | `ls` `read_file` `write_file` `edit_file` `delete` `glob` `grep`（backend 支持执行时再加 `execute`） |
| 2 | `SubAgentMiddleware` | `task` 工具 + 内置 `general-purpose` 子代理 |
| 3 | `create_summarization_middleware(...)` | 历史过长时压缩，原文卸载到文件 |
| 4 | `PatchToolCallsMiddleware` | 修补「有 tool_call 无 ToolMessage」的悬空调用（中断恢复后常见） |
| 尾部 | `SkillsMiddleware` / `MemoryMiddleware` / `HumanInTheLoopMiddleware` | 仅当传了 `skills=` / `memory=` / `interrupt_on=` 才挂 |

你传的 `middleware=[...]` 插在核心栈之后、尾部之前。另外图默认 `recursion_limit=9999`——长程代理跑几百步是常态。

## 3. 支柱一：规划工具 `write_todos`（0.7 起 opt-in）

0.7.0 之前它是默认项；**0.7 起默认没有**。官方评测显示对强模型它不显著提分还多花钱，因此改成按需开启。适合三种场景：步骤很长的任务、能力较弱的模型、需要把进度展示给用户的 UI。

```python
from langchain.agents.middleware import TodoListMiddleware

agent = create_deep_agent(model=model, middleware=[TodoListMiddleware()])
out = agent.invoke(...)
out["todos"]   # [{"content": "...", "status": "pending|in_progress|completed"}, ...]
```

要点：`write_todos` 本身不执行任何事，它只是把计划写进 state 的 `todos` 通道。价值在于「每轮都能看到计划」这一上下文工程效果——一个 no-op 工具换来注意力锚点。声明式子代理**不继承**主代理的这个 opt-in，要各自在 `middleware` 里加。

## 4. 支柱二：虚拟文件系统与 backend

文件工具不直接碰磁盘，而是经过 **backend**。默认 `StateBackend()`：文件存在图 state 的 `files` 键里，随 checkpoint 持久化，线程之间隔离。

| backend | 存在哪 | 生命周期 | 典型用途 |
| --- | --- | --- | --- |
| `StateBackend()` | state `files` | 单个 thread | 草稿、中间结果（默认） |
| `StoreBackend(namespace=..., store=...)` | LangGraph `BaseStore` | 跨 thread | 长期记忆 |
| `FilesystemBackend(root_dir=..., virtual_mode=True)` | 真磁盘 | 永久 | 编码代理改真实仓库 |
| `LocalShellBackend` / 沙箱 | 磁盘 + shell | — | 额外开出 `execute` 工具 |
| `CompositeBackend(default=..., routes={...})` | 按路径前缀路由 | 混合 | `/memories/` 进 store，其余进 state |

```python
backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend(namespace=lambda rt: ("user-42",), store=store)},
)
agent = create_deep_agent(model=model, backend=backend, store=store)
```

为什么文件系统是上下文工程的核心：工具返回 5 万字网页时，代理可以 `write_file` 存下、只在消息里留路径，之后用 `grep` / `read_file(offset, limit)` 按需取回。上下文窗口变成「工作记忆」，文件系统变成「外存」。

访问控制用 `permissions=[FilesystemPermission(operations=["write"], paths=["/src/**"], mode="deny")]`，`mode` 取 `allow` / `deny` / `interrupt`。

## 5. 支柱三：子代理 `task`

主代理调用 `task(description=..., subagent_type=...)`，库会用**全新的上下文**跑一个子代理，只把它的**最终消息**作为 `ToolMessage` 回传。子代理的几十轮中间过程不会进入父上下文——这就是「上下文隔离」。

```python
researcher = {
    "name": "researcher",                 # 必填
    "description": "深入调研单个子问题",    # 必填：主模型据此决定派给谁
    "system_prompt": "你是严谨的研究员，只回传结论与出处。",
    "tools": [web_search],                # 可选，缺省继承主代理工具
    "model": "deepseek:deepseek-v4-pro",  # 可选，缺省同主代理
}
agent = create_deep_agent(model=model, subagents=[researcher])
```

- `SubAgent` 还可带 `middleware`、`interrupt_on`、`skills`、`permissions`、`response_format`。
- 已有 LangGraph 图？用 `CompiledSubAgent(name=..., description=..., runnable=graph)` 直接挂上。
- 不传 `subagents` 也会有内置 `general-purpose` 子代理，主代理可以把任何子任务丢给「自己的分身」。
- 多个 `task` 调用可出现在同一条 AIMessage 里并行执行——这是 fan-out 调研的天然写法。
- `mode="fork"`（实验性）让子代理延续父对话，而不是从空白开始。

## 6. 支柱四：系统提示与中间件

0.7 起内置的长篇 base prompt 被清空（官方认为它与工具 schema 重复）。**你的 `system_prompt` 就是主要的行为说明**：写清楚流程（先计划？结果写哪个文件？何时派子代理？）。想要旧版提示可显式传 `system_prompt=BASE_AGENT_PROMPT`（已弃用，0.9 移除）。

其他常用开关：

| 参数 | 作用 |
| --- | --- |
| `interrupt_on={"write_file": True}` | 工具执行前人工审批（需 `checkpointer`），机制同 LangGraph 第 4 阶段 |
| `memory=["/AGENTS.md"]` | 启动时从 backend 读入记忆文件，拼进系统提示 |
| `skills=["/skills/"]` | 按需披露的技能目录（SKILL.md），与本仓库 skill 思路一致 |
| `response_format=Schema` | 结构化输出，同 `create_agent` |
| `checkpointer=` / `store=` | 短期持久化 / 长期存储 |

## 7. 与手写 ReAct / LangGraph 对比

| 维度 | 手写 LangGraph ReAct | `create_agent` | `create_deep_agent` |
| --- | --- | --- | --- |
| 抽象层级 | 节点 + 边 | 循环 + 中间件 | 预装中间件的 harness |
| 文件 / 外存 | 自己实现 | 自己加 | 内置，backend 可换 |
| 子代理 | 子图 + `Send` 手写 | 自己包成工具 | `task` 内置 |
| 计划 | 无 | 可加 `TodoListMiddleware` | 同左（0.7 起 opt-in） |
| 上下文压缩 | 无 | 可加 `SummarizationMiddleware` | 默认开启 |
| 控制粒度 | 最细 | 中 | 最粗，靠参数和中间件定制 |
| 适合 | 流程固定、需精确控制 | 一般工具代理 | 开放式长程任务：调研、编码、写作 |

选择原则：流程能画成固定的图，就用 LangGraph；步骤数事先未知、需要几十上百轮自主探索，用 deepagents。两者不冲突——deep agent 本身就是图，也可以作为节点嵌进更大的图。

## 8. 常见坑

1. **照抄老教程找不到 `write_todos`**：0.7 起要显式 `middleware=[TodoListMiddleware()]`。
2. **以为文件写到了磁盘**：默认 `StateBackend`，文件只在 `out["files"]` 里；要落盘用 `FilesystemBackend`。
3. **`FilesystemBackend` 路径报 `ValueError`**：0.7 起默认 `virtual_mode=True`，路径被锚定在 `root_dir` 下，禁止 `..` 越界。
4. **`write_file` 静默覆盖**：0.7 起文件存在时直接整体替换，不再报错；要保护内容请用 `permissions` 或 `interrupt_on`。
5. **`delete` 是递归的**：有 write 权限就能删整个子树，记得加 deny 规则。
6. **子代理 `description` 写得含糊**：主模型只靠它路由，描述不清就永远不会被派活。
7. **期待子代理回传中间过程**：父代理只收到最终消息；要细节就让子代理把结果写进文件再回传路径。
8. **不传 `model`**：退回 Anthropic 默认模型并发弃用告警，没装 `langchain-anthropic` 会直接报错。
9. **`interrupt_on` 不生效**：没配 `checkpointer`，或 `invoke` 时没给 `thread_id`。

## 9. 自检

`check.py` 用脚本化假模型验证了五个结论：默认工具集没有 `write_todos`；opt-in 后 `todos` 进入 state；`write_file` / `edit_file` 落在 `out["files"]`；子代理只回传最终消息；`CompositeBackend` 把 `/memories/` 路由到 store。练习题见 `qa.ipynb`。

## 10. 参考

- 源码：<https://github.com/langchain-ai/deepagents>（`libs/deepagents/deepagents/graph.py` 看中间件拼装顺序）
- 文档：<https://docs.langchain.com/oss/python/deepagents/overview>
- 0.7.0 发布说明：<https://github.com/langchain-ai/deepagents/releases/tag/deepagents%3D%3D0.7.0>
- 博客 Deep Agents v0.7（todo opt-in 的评测依据）：<https://www.langchain.com/blog/deep-agents-v0-7>
- todo opt-in PR：<https://github.com/langchain-ai/deepagents/pull/4929>
- 前置：`codes/langchain/10_middleware`、`codes/summary/langchain-middleware.html`、`codes/langgraph/index.md`
