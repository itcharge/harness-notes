# harnex/loop/agent.py —— Harnex v0.4：事件落进日志，消息由日志投影
import asyncio
import json

from build_registry import build_registry
from llm import chat
from session.log import SessionLog, project
from skills import SkillPackLoader

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
        print("Harnex>", await run_turn(q, registry, log, system))


if __name__ == "__main__":
    asyncio.run(main())
