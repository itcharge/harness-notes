# harnex/loop/agent.py —— Harnex v0.3：系统提示里多一段技能清单，循环逻辑一行没改
import asyncio
import json

from build_registry import build_registry
from llm import chat
from skills import SkillPackLoader

MAX_STEPS = 8
BASE_PROMPT = "你是一个能读写文件、执行任务的助手。回答简短、准确，不确定就问。"


def build_system_prompt(loader: SkillPackLoader) -> str:
    catalog = loader.catalog()
    return f"{BASE_PROMPT}\n\n{catalog}" if catalog else BASE_PROMPT


async def run(user_input: str, registry, system: str) -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_input}]
    for step in range(MAX_STEPS):
        msg = chat(messages, tools=registry.schemas())
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = await registry.call(call.function.name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "（步数超限，已强制停止）"


async def main() -> None:
    registry = build_registry()
    loader = SkillPackLoader()
    loader.discover()
    system = build_system_prompt(loader)
    print(f"已加载 {len(loader.packs)} 个技能包，清单 {len(loader.catalog())} 字符")
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", await run(q, registry, system))


if __name__ == "__main__":
    asyncio.run(main())
