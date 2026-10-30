"""离线自检：用脚本化假模型驱动 create_deep_agent，不调真实 API。

python codes/deepagents/01_harness_basics/check.py
"""
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend


class ScriptedModel(GenericFakeChatModel):
    """按顺序吐出预设 AIMessage；记录每次 bind_tools 看到的工具名。"""

    seen_tools: list = []

    def bind_tools(self, tools, **kw):
        self.seen_tools.append(sorted(t.name if hasattr(t, "name") else t["name"] for t in tools))
        return self


def call(name, args, i):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


def ask(agent, text="go"):
    return agent.invoke({"messages": [{"role": "user", "content": text}]})


FS = {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep"}


def test_default_tools_have_no_todos():
    m = ScriptedModel(messages=iter([AIMessage("ok")]))
    ask(create_deep_agent(model=m))
    tools = set(m.seen_tools[-1])
    assert FS | {"task"} <= tools, tools
    assert "write_todos" not in tools  # 0.7 起 todo 是 opt-in


def test_todos_opt_in():
    script = [call("write_todos", {"todos": [{"content": "调研", "status": "in_progress"}]}, 1), AIMessage("ok")]
    m = ScriptedModel(messages=iter(script))
    out = ask(create_deep_agent(model=m, middleware=[TodoListMiddleware()]))
    assert "write_todos" in m.seen_tools[-1]
    assert out["todos"][0]["content"] == "调研"


def test_virtual_fs_lives_in_state():
    script = [call("write_file", {"file_path": "/plan.md", "content": "v1"}, 1),
              call("edit_file", {"file_path": "/plan.md", "old_string": "v1", "new_string": "v2"}, 2),
              AIMessage("ok")]
    out = ask(create_deep_agent(model=ScriptedModel(messages=iter(script))))
    assert out["files"]["/plan.md"]["content"] == "v2"


def test_subagent_context_isolation():
    sub_model = ScriptedModel(messages=iter([AIMessage("子代理结论：42")]))
    script = [call("task", {"description": "算答案", "subagent_type": "researcher"}, 1), AIMessage("ok")]
    agent = create_deep_agent(
        model=ScriptedModel(messages=iter(script)),
        subagents=[{"name": "researcher", "description": "做调研", "system_prompt": "你是研究员", "model": sub_model}],
    )
    out = ask(agent)
    tool_msgs = [m for m in out["messages"] if m.type == "tool"]
    assert tool_msgs[0].content.strip().endswith("42")  # 父代理只拿到最终答复
    assert not any("你是研究员" in str(m.content) for m in out["messages"])


def test_composite_backend_routes_memories_to_store():
    store = InMemoryStore()
    backend = CompositeBackend(default=StateBackend(),
                               routes={"/memories/": StoreBackend(namespace=lambda rt: ("demo",), store=store)})
    script = [call("write_file", {"file_path": "/memories/pref.md", "content": "简洁"}, 1),
              call("write_file", {"file_path": "/scratch.md", "content": "tmp"}, 2), AIMessage("ok")]
    out = ask(create_deep_agent(model=ScriptedModel(messages=iter(script)), backend=backend, store=store))
    assert "/scratch.md" in out["files"] and "/memories/pref.md" not in out["files"]
    assert store.search(("demo",)), "长期记忆应落在 store"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
