# harnex/loop/agent.py —— Harnex v0.1：七十行，一个完整的 Agent
import json
from datetime import datetime
from llm import chat          # 第 2 章的适配层：唯一接触模型 SDK 的地方

MAX_STEPS = 8                 # 熔断上限：任何 Agent 都必须有


# --- 工具：统一接口——收一个参数字典，返回一个字符串 ---
def get_time(args: dict) -> str:
    """返回当前日期和时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def get_weather(args: dict) -> str:
    """返回某城市今天的天气（教学用模拟数据）。"""
    return f"{args['city']}：晴，26℃"


# --- 工具清单：给模型看的"菜单"（模型不执行，只照着它点菜）---
TOOLS = {
    "get_time": get_time,
    "get_weather": get_weather,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取当前日期和时间。凡是涉及『今天 / 现在 / 几号』的问题都必须先调用它。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市今天的天气。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如 '上海'"},
                },
                "required": ["city"],
            },
        },
    },
]


# --- 循环本体：想 → 做 → 看 → 再想 ---
def run(user_input: str) -> str:
    messages = [{"role": "user", "content": user_input}]
    for _ in range(MAX_STEPS):                              # ④ 熔断：最多转这么多圈
        msg = chat(messages, tools=TOOL_SCHEMAS)            # ① 想：把历史和菜单发过去
        messages.append(msg)                                # ② 记：把这一步也存进历史
        if not msg.tool_calls:                              # ③ 停：模型说"我不需要工具了"
            return msg.content
        for call in msg.tool_calls:                         # ⑤ 做：逐个执行模型点名的工具
            fn = TOOLS[call.function.name]                  #    按名字取出要执行的函数
            args = json.loads(call.function.arguments)      #    模型给的参数：一段 JSON 文本
            result = fn(args)                               #    把参数字典整个交给工具
            messages.append({"role": "tool",                # ⑥ 看：把结果回填给模型
                             "tool_call_id": call.id,
                             "content": str(result)})
    return "（步数超限，已强制停止）"


if __name__ == "__main__":
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", run(q))
