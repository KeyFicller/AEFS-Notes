# LangGraph 分阶段练习

练习放在 `codes/langgraph/{阶段目录}/qa.ipynb`。需要读写文件时，工作空间就是该阶段目录。

出题 / 审阅 / 出卡习惯对齐 `python-base-qa`：一次只做一个阶段；出题不写答案；出卡才生成该阶段的 `card.png`。

模型：统一用真实 API（`init_chat_model`，如 `deepseek:deepseek-v4-flash`），密钥读 `DEEPSEEK_API_KEY`（可放 `codes/langgraph/local.env`）。

本模块是 LangGraph 专线，与 `codes/langchain/` 分开：LangChain 线到 `08_agents` 用手写循环收束，这里把同一个 Agent 改写成显式图 + checkpoint。

| 阶段 | 目录 | 焦点 |
| --- | --- | --- |
| 1 | `01_state_graph` | `StateGraph`、`State` TypedDict、`add_messages` reducer、节点 / 静态边、`compile` / `invoke` |
| 2 | `02_conditional_edges` | 路由函数、`END`、手写 ReAct 图（agent ↔ tools 循环） |
| 3 | `03_checkpointer_threads` | `MemorySaver`、`thread_id`、`get_state`、`get_state_history` |
| 4 | `04_interrupts_hitl` | `interrupt_before` / `after`、`Command(resume=...)`、`update_state` |
| 5 | `05_streaming` | `stream(mode="updates"/"values"/"messages")`、`astream` |
| 6 | `06_prebuilt_react` | `ToolNode`、预置 ReAct agent、手写图 vs 预置 |
| 7 | `07_persistence_send_subgraph` | `SqliteSaver` / Postgres 落盘、`Send` fanout、子图、durable execution |
