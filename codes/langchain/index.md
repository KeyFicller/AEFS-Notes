# LangChain 分阶段练习

练习放在 `codes/langchain/{阶段目录}/qa.ipynb`。需要读写文件时，工作空间就是该阶段目录。

出题 / 审阅 / 出卡习惯对齐 `python-base-qa`：一次只做一个阶段；出题不写答案；出卡才生成该阶段的 `card.png`。

模型：统一用真实 API（`init_chat_model`，如 `deepseek:deepseek-v4-flash`），密钥读 `DEEPSEEK_API_KEY`（可放 `codes/langchain/local.env`）。**不再使用 FakeModel。** LangGraph 另开模块，不在本线。

| 阶段 | 目录 | 焦点 |
| --- | --- | --- |
| 1 | `01_messages_model` | Message 类型、ChatModel 调用 |
| 2 | `02_prompts` | PromptTemplate / ChatPromptTemplate |
| 3 | `03_lcel_chains` | LCEL `\|` 组链、Runnable |
| 4 | `04_tools` | `@tool`、工具 schema、`bind_tools` |
| 5 | `05_docs_split` | 文档加载、文本切分 |
| 6 | `06_embeddings_store` | Embedding、向量库写入 / 查询 |
| 7 | `07_rag_chain` | 检索 + 组 RAG 链 |
| 8 | `08_agents` | Agent / 工具调用闭环（非 LangGraph 专篇） |
