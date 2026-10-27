# 一次带工具调用的对话：单轮，还没有循环
import json
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)
MODEL = "deepseek-flash"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市的当前天气。用户问到天气时调用。",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名，如 杭州"}},
            "required": ["city"],
        },
    },
}]

def get_weather(args: dict) -> str:
    return f"{args['city']}：小雨，18~24℃"  # 教学版；真实场景要调 API（第 4 章）

def chat(user_input: str) -> str:
    messages = [{"role": "user", "content": user_input}]
    msg = client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOLS
    ).choices[0].message

    if not msg.tool_calls:
        return msg.content

    call = msg.tool_calls[0]
    result = get_weather(json.loads(call.function.arguments))
    messages += [msg, {"role": "tool", "tool_call_id": call.id, "content": result}]

    final = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    return final.choices[0].message.content

print(chat("杭州今天天气怎么样？"))
