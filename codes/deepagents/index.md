# Deep Agents 分阶段练习

练习放在 `codes/deepagents/{阶段目录}/`。讲义是各阶段的 `README.md`，速查页是 `codes/summary/deepagents.html`。

本模块接在 `codes/langchain/10_middleware` 和 `codes/langgraph/` 之后：`deepagents` 不是新框架，而是把 `create_agent` + 一组官方中间件预先装好的 **agent harness**，产物仍是一张 LangGraph `CompiledStateGraph`。

版本：对照本机 `deepagents 0.7.32` / `langchain 1.4.7` / `langgraph 1.2.18` 核对。0.7 有破坏性变更（todo 改为 opt-in、base prompt 清空、`delete` 工具），老教程里的写法要先对一下。

模型：练习用真实 API（`init_chat_model("deepseek:...")`，密钥读 `DEEPSEEK_API_KEY`）；`check.py` 用脚本化假模型，离线可跑。

| 阶段 | 目录 | 焦点 |
| --- | --- | --- |
| 1 | `01_harness_basics` | `create_deep_agent`、虚拟文件系统与 backend、`task` 子代理、opt-in 的 `write_todos`、中间件栈、与手写 ReAct 的对比 |
