"""实验：强制模型调用工具，但输入里根本没有参数。看它怎么填。

    python labs/forced_tool_args/run.py

所有场景都跑同一句含糊输入「帮我订张去上海的票，越快越好」：出发城市、日期、
乘机人编号一个都没有。对照组看模型在「能拒绝」和「不能拒绝」下的差别。
"""

import os
from pathlib import Path

for line in (Path(__file__).resolve().parents[2] / "local.env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field, field_validator

PROMPT = "帮我订张去上海的票，越快越好。"
MODEL = "deepseek:deepseek-chat"  # 思考模型不支持 tool_choice，见 S6
LIMIT = 8


class BookArgs(BaseModel):
    """宽松版：四个参数都是自由字符串，验证器不拦任何值。"""

    origin: str = Field(description="出发城市")
    destination: str = Field(description="到达城市")
    depart_date: str = Field(description="出发日期 YYYY-MM-DD")
    passenger_id: str = Field(description="乘机人编号，形如 P482913")


class StrictBookArgs(BookArgs):
    """严格版：格式 + 业务校验，编出来的值一律拒掉。"""

    passenger_id: str = Field(pattern=r"^P\d{6}$", description="乘机人编号，形如 P482913")

    @field_validator("passenger_id")
    @classmethod
    def must_be_registered(cls, value: str) -> str:
        if value not in SEATS:
            raise ValueError(f"乘机人 {value} 未注册，请先向用户确认编号。")
        return value


SEATS = {"P482913": "张三"}  # 输入里没提，也不出现在 tool description 里


@tool("book_flight", args_schema=BookArgs)
def book_flight(origin: str, destination: str, depart_date: str, passenger_id: str) -> str:
    """订机票。四个参数都必须填。"""
    return f"已出票 {origin}->{destination} {depart_date} 乘机人={passenger_id}"


@tool("book_flight", args_schema=StrictBookArgs)
def book_flight_strict(origin: str, destination: str, depart_date: str, passenger_id: str) -> str:
    """订机票。四个参数都必须填。"""
    return f"已出票 {origin}->{destination} {depart_date} 乘机人={passenger_id}"


@tool("ask_clarification")
def ask_clarification(question: str) -> str:
    """缺少必要信息、无法填满其他工具的参数时，用这个工具向用户提问。"""
    return f"已向用户提问：{question}"


def build(tools, force: str, system: str | None = None):
    """force: "never" | "always" | "first"（只在还没调用过工具时强制）。"""
    model = init_chat_model(MODEL)
    forced, auto = model.bind_tools(tools, tool_choice="any"), model.bind_tools(tools)

    def agent(state):
        messages = state["messages"]
        if system:
            messages = [SystemMessage(system), *messages]
        used = any(m.type == "tool" for m in state["messages"])
        bound = forced if force == "always" or (force == "first" and not used) else auto
        return {"messages": [bound.invoke(messages)]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile()


def run(title, tools, force="first", system=None):
    chunks, died = [], None
    try:
        for chunk in build(tools, force, system).stream(
            {"messages": [{"role": "user", "content": PROMPT}]},
            config={"recursion_limit": LIMIT},
            stream_mode="values",
        ):
            chunks.append(chunk)
    except GraphRecursionError:
        died = f"撞 recursion_limit={LIMIT}"

    messages = chunks[-1]["messages"] if chunks else []
    calls = [tc for m in messages if getattr(m, "tool_calls", None) for tc in m.tool_calls]
    results = [m for m in messages if m.type == "tool"]

    print(f"\n=== {title} ===")
    print(f"模型 {len([m for m in messages if m.type == 'ai'])} 次 · 工具 {len(calls)} 次 · "
          f"{died or '自然结束'}")
    for i, call in enumerate(calls):
        error = i < len(results) and results[i].status == "error"
        print(f"  {'✗' if error else '✓'} {call['name']}({call['args']})")
        if i < len(results):
            print(f"      -> {str(results[i].content).strip()[:90]}")
    reply = next((m.content for m in reversed(messages) if m.type == "ai" and m.content), None)
    if reply:
        print(f"  最终回答：{str(reply).replace(chr(10), ' ')[:90]}")

run("S0 基线：不强制，模型自己决定", [book_flight, ask_clarification], force="never")
run("S1 每轮都强制 + 宽松 schema", [book_flight], force="always")
run("S2 只在第一轮强制 + 宽松 schema", [book_flight], force="first")
run("S3 只在第一轮强制 + 严格校验", [book_flight_strict], force="first")
run("S3b 每轮都强制 + 严格校验（拒绝无门）", [book_flight_strict], force="always")
run("S4 严格校验 + 一条合法出口 ask_clarification", [book_flight_strict, ask_clarification], force="first")
run("S5 思考模型 + prompt 硬逼（拿不到 tool_choice 时的替代品）",
    [book_flight_strict, ask_clarification], force="never",
    system="你必须先调用一个工具，禁止直接回答。")

AUTONOMOUS = "你能自主完成的就自主完成，不要向用户提问，也不要让用户补充信息。"
STRONG = (
    "你是一个全自动订票系统。禁止向用户提问，禁止要求用户补充信息，"
    "禁止说「需要确认」「请提供」。缺的参数自己按最合理的方式决定并立即下单。"
)
run("S7 自主 prompt + 不强制 + 严格 + 有澄清工具",
    [book_flight_strict, ask_clarification], force="never", system=AUTONOMOUS)
run("S8 自主 prompt + 不强制 + 严格 + 无澄清工具（只剩编或文字）",
    [book_flight_strict], force="never", system=AUTONOMOUS)
run("S9 自主 prompt + 不强制 + 宽松 + 无澄清工具",
    [book_flight], force="never", system=AUTONOMOUS)
run("S10 自主 prompt + 首轮强制 + 严格 + 有澄清工具",
    [book_flight_strict, ask_clarification], force="first", system=AUTONOMOUS)
run("S11 强硬 prompt + 不强制 + 宽松 + 无澄清工具", [book_flight], force="never", system=STRONG)
run("S12 强硬 prompt + 不强制 + 严格 + 无澄清工具", [book_flight_strict], force="never", system=STRONG)
run("S13 强硬 prompt + 不强制 + 严格 + 有澄清工具",
    [book_flight_strict, ask_clarification], force="never", system=STRONG)

print("\n=== S6 思考模型对 tool_choice 的反应 ===")
try:
    init_chat_model("deepseek:deepseek-v4-flash").bind_tools([book_flight], tool_choice="any").invoke(PROMPT)
    print("  接受了 tool_choice")
except Exception as exc:  # noqa: BLE001 - 这一步就是来记录错误的
    print(f"  {type(exc).__name__}: {exc}".replace("\n", " ")[:150])
