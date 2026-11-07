# harnex/loop/agent.py —— Harnex v0.7：清单每轮重建，拼进系统提示
import asyncio
import json

from build_registry import build_registry
from llm import chat
from planning.todos import make_todo_tools, project_todos, render_todos
from session.log import SessionLog, project
from skills import SkillPackLoader
from tools import Tool

MAX_STEPS = 8
BASE_PROMPT = "你是一个能读写文件、执行任务的助手。回答简短、准确，不确定就问。"


def build_system_prompt(loader: SkillPackLoader) -> str:
    catalog = loader.catalog()
    return f"{BASE_PROMPT}\n\n{catalog}" if catalog else BASE_PROMPT


async def run_turn(user_input: str, registry, log: SessionLog,
                   system: str = BASE_PROMPT) -> str:
    log.append("user_message", content=user_input)
    messages = [{"role": "system", "content": system}] + project(log.events())
    for _ in range(MAX_STEPS):
        msg = chat(messages, tools=registry.schemas())
        record = msg.model_dump()               # SDK 对象 → 可写进 JSON 的字典
        log.append("assistant_message", message=record)
        messages.append(record)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = await registry.call(call.function.name, args)
            log.append("tool_result", tool_call_id=call.id,
                       name=call.function.name, content=result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "（步数超限，已强制停止）"


async def run_task(goal: str, registry, log: SessionLog, system: str = BASE_PROMPT) -> str:
    log.append("user_message", content=goal)
    set_todos, update_todo = make_todo_tools(log)
    # 同一进程里第二次进任务时，两个工具已经在表里了——4.1 那条「重名拒」会拦下重装
    installed = {schema["function"]["name"] for schema in registry.schemas()}
    if "set_todos" not in installed:
        registry.register(Tool("set_todos", "写入或替换整张待办清单。开始一个多步任务时先调它。",
                               {"type": "object", "required": ["items"],
                                "properties": {"items": {"type": "array"}}},
                               set_todos, ["plan:write"]))
        registry.register(Tool("update_todo", "更新清单某一项的状态。每完成一项都要调它。",
                               {"type": "object", "required": ["index", "status"],
                                "properties": {"index": {"type": "integer"},
                                               "status": {"type": "string"},
                                               "note": {"type": "string"}}},
                               update_todo, ["plan:write"]))

    for _ in range(MAX_STEPS):
        messages = project(log.events())
        todos_text = render_todos(project_todos(log.events()))
        system_with_todos = system + "\n\n" + todos_text
        messages.insert(0, {"role": "system", "content": system_with_todos})
        msg = chat(messages, tools=registry.schemas())
        record = msg.model_dump()               # SDK 对象 → 可写进 JSON 的字典
        log.append("assistant_message", message=record)
        messages.append(record)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = await registry.call(call.function.name, args)
            log.append("tool_result", tool_call_id=call.id,
                       name=call.function.name, content=result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "（步数超限，已强制停止）"


async def main() -> None:
    registry = build_registry()
    loader = SkillPackLoader()
    loader.discover()
    system = build_system_prompt(loader)
    log = SessionLog()                  # 只建一次：同一会话的每一轮都往这儿追加
    print(f"已加载 {len(loader.packs)} 个技能包，清单 {len(loader.catalog())} 字符")
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", await run_task(q, registry, log, system))


if __name__ == "__main__":
    asyncio.run(main())
