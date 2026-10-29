# harnex/llm/client.py —— 全书唯一直接接触模型 SDK 的地方
import os
from openai import OpenAI

_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)
_model = "deepseek-flash"  # 换供应商时，连同上面的 Key、base_url 一起改

def chat(messages, tools=None, temperature=0.0):
    kwargs = {"temperature": temperature}
    if tools:
        kwargs["tools"] = tools
    resp = _client.chat.completions.create(
        model=_model,
        messages=messages,
        **kwargs,
    )
    return resp.choices[0].message
