# harnex/loop/agent.py —— Harnex v0.2：循环只认识注册表
import asyncio
import json

from build_registry import build_registry
from llm import chat
from tools import ToolRegistry

MAX_STEPS = 8


async def run(user_input: str, registry: ToolRegistry) -> str:
    messages = [{"role": "user", "content": user_input}]
    for step in range(MAX_STEPS):
        msg = chat(messages, tools=registry.schemas())       # 菜单由注册表生成
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = await registry.call(call.function.name, args)  # MCP 工具要等，本地工具也照样能用
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "（步数超限，已强制停止）"


if __name__ == "__main__":
    reg = build_registry()
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", asyncio.run(run(q, reg)))
