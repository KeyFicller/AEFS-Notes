"""生产版 plan / act / observe。

main.py 自己转循环。这里把循环交给 LangChain 的 create_agent，底层是 LangGraph。
模型走 DeepSeek 托管 API，客户端是 langchain-deepseek 的 ChatDeepSeek。

PyTorch 不在这条链路里。它负责张量、训练和本地前向。
DeepSeek 的权重在对方机房，这里只发 HTTP。本地再用 PyTorch 跑一遍推理，
不会让这个 agent 更接近生产，只是多一个用不上的依赖。
本地模型（Ollama、vLLM）才是 PyTorch 出现的地方。

和 main.py 的对应：
- agent_loop           -> create_agent 的 model / tools 循环
- Budget.max.turns     -> invoke 的 recursion_limit
- HookBus              -> callbacks，这里只用来打印
- tool_read_file 等    -> 继续用 main.py 的沙箱。框架不提供目录监狱
- SCRIPT / model_step  -> 删掉。工具结果留在 messages 里，下一轮模型能看见

密钥：环境变量 DEEPSEEK_API_KEY，没有则由 common.load_local_env 读 deskpet/local.env。
模型：环境变量 DEEPSEEK_MODEL，默认 deepseek-v4-flash（支持工具调用）。
"""

import os
import sys
from pathlib import Path
from typing import Any

_CAPSTONE = Path(__file__).resolve().parents[1]
if str(_CAPSTONE) not in sys.path:
    sys.path.insert(0, str(_CAPSTONE))

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.errors import GraphRecursionError

from common import load_local_env
from demo_main import destructive_guard, tool_read_file, tool_run_shell

# 一次模型调用和一次工具调用各算图上的一步。8 轮工具大约是 20 步。
RECURSION_LIMIT = 20
DEFAULT_MODEL = "deepseek-v4-flash"

SYSTEM_PROMPT = """你是终端里的编码助手，工作区只有当前目录。

- 用 read_file 读文件，路径相对工作区。
- 用 run_shell 跑程序。它不是 shell，不解释 &&、管道和重定向。
- 不要读工作区外面的路径。
- 先拿到工具结果再下结论。任务完成就直接回答，不要再调工具。
"""


def make_tools(sandbox: str) -> list:
    """工具的参数里没有 sandbox。模型只能传路径和命令，根目录由我们定。"""

    @tool
    def read_file(path: str) -> str:
        """读取工作区内的文本文件。path 相对工作区根目录。"""
        return tool_read_file(sandbox, path)

    @tool
    def run_shell(command: str) -> str:
        """在工作区运行一个程序。command 是一行参数，例如 ls 或 python3 -c 'print(1)'。"""
        # 拒绝名单仍然是演示。shell=False 挡得住管道，挡不住 argv 形式的 rm。
        decision = destructive_guard({"args": {"command": command}})
        if decision.get("blocked"):
            return str(decision.get("reason", "blocked"))
        return tool_run_shell(sandbox, command)

    return [read_file, run_shell]


class TracePrinter(BaseCallbackHandler):
    """main.py 的 HookBus 在这里收成回调。框架负责调用顺序，我们只旁路打印。"""

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        print(f"tool start  {serialized.get('name', '')}  {input_str}")

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        text = str(output)
        print(f"tool end    bytes={len(text)}")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        print(f"tool error  {error}")


def final_text(messages: list) -> str:
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        content = message.content
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def token_total(messages: list) -> tuple[int, int]:
    calls = 0
    tokens = 0
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        calls += 1
        usage = message.usage_metadata or {}
        tokens += int(usage.get("total_tokens") or 0)
    return calls, tokens


def build_model() -> ChatDeepSeek:
    # 思考模式默认开着时，多轮工具调用要把 reasoning_content 原样带回。
    # 这个脚手架关掉思考，避免第二轮 400。要推理链时再打开，并确认客户端会回传该字段。
    return ChatDeepSeek(
        model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
        temperature=0,
        max_retries=2,
        extra_body={"thinking": {"type": "disabled"}},
    )


def run(task: str, sandbox: str) -> str:
    agent = create_agent(
        model=build_model(),
        tools=make_tools(sandbox),
        system_prompt=SYSTEM_PROMPT,
    )
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={
                "recursion_limit": RECURSION_LIMIT,
                "callbacks": [TracePrinter()],
            },
        )
    except GraphRecursionError:
        print(f"stop        recursion_limit {RECURSION_LIMIT} reached")
        return ""

    messages = result["messages"]
    calls, tokens = token_total(messages)
    print("-" * 80)
    print(f"model calls={calls}  tokens={tokens}")
    print("-" * 80)
    text = final_text(messages)
    print(text)
    return text


def main() -> None:
    load_local_env(Path(__file__).resolve().parent)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("缺少 DEEPSEEK_API_KEY。可写在环境变量或 deskpet/local.env。")

    task = " ".join(sys.argv[1:]).strip() or (
        "读取工作区里的 test_file.txt，原样告诉我里面写了什么。"
    )
    sandbox = str(Path(__file__).resolve().parent)
    run(task, sandbox)


if __name__ == "__main__":
    main()
