# 2.3 从对话到交付：tool use、结构化输出与模型选型

2.2 节的最后一句是：prompt 再好，也只是发动机的点火钥匙。钥匙拧完，还得有人去办事。

你对它说「查一下杭州天气」。模型不会自己去查。它返回一段约定好的 JSON，意思是：请调用 `get_weather`，参数是 `city=杭州`。这次调用就结束了。真正去查的，是你写的函数。

```text
你 ─ 发出：工具清单 + 用户消息 ──────────► 模型
                                          │ 决定：我要调 get_weather
你 ◄ ─ 返回：{"name":"get_weather", ...} ──┘
你 ─ 真的执行 get_weather(杭州)  ← 执行权在你手里
你 ─ 把结果回填进 messages ──────────────► 模型
                                           │ 下一步：直接用结果回答 / 再调一个工具
你 ◄ ─ 返回：最终答复 ────────────────────────┘
```

> **工具调用，就是模型替你写好了函数参数。执行权在你手里。**

模型决定调哪个、参数填什么；你执行，再把结果塞回 `messages`。执行权留在你这边，后面才能规定哪些工具能直接用、哪些必须先问人（第 15 章）。

## 2.3.1 调用一次工具

下面这段只有一轮：模型点一次工具，你执行，它再说一句。还没有循环。客户端和第 2.1 节相同，换供应商只改 Key、`base_url` 和模型名。

```python
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
```

`get_weather` 收到的是一个字典，例如 `{"city": "杭州"}`，也就是模型返回的 `arguments` 解析之后的结果。第 4 章的工具注册表、MCP 的 `inputSchema`，用的是同一个约定。

对着代码看三件事：

1. **模型被调用了两次。** 第一次返回 `tool_calls`，第二次「看着工具结果说话」（返回最终答复）。这两次调用，加上中间的 `get_weather`，才是一次完整的「工具调用」。
2. **真正执行工具的是 `get_weather` 这个函数，以及 `chat` 里调用它的那一行（`result = get_weather(...)`）**。模型没有碰过这个函数。
3. **它没做的事**：它不会循环、不会自己再调第二个工具、也不会记得你上一轮说了什么。这三件事分别是第 3 章（循环）、第 4 章（多工具登记、调用）、第 6 章（记忆）的相关内容。


> 这段代码 **刻意没有循环**，它只能调用一个工具、回答一次。第 3 章我们要做的，就是给它加上「做一步、看结果、再决定下一步」的循环 —— 对应大约 75 行代码，也是全书的核心。

## 2.3.2 让输出能被程序读

Agent 内部各步骤之间传递的信息，很多不是给人看的，而是给下一段程序用的。这时就要用到 **结构化输出**：让模型按固定的字段返回 JSON，而不是一段自由文本。

```text
自由文本（给人看）:  "这段代码有个问题，在第三行，可能会出现数组越界……"

结构化输出（给程序用）: {"line": 3, "issue": "array_index", "severity": "high"}
```

什么时候用哪个，看结果交给谁：

| 结果给谁    | 用什么   | 例子             |
| ------- | ----- | -------------- |
| 给人看     | 自由文本  | 聊天回复、解释说明      |
| 给程序接着处理 | 结构化输出 | 工具参数、分类结果、待办清单 |

主要注意的是：**结构化输出能大幅减少解析失败，但不能消除。** 即使加了 schema 约束，在极端情况下仍可能返回格式有偏的内容。所以第 10 章会专门讲「防御性解析」—— 永远假设它会出错，并准备好兜底：先校验，校验不过就重试或停下来。

## 2.3.3 费用和等待时间

Agent 会花钱，也会花时间让人等。

**成本**：按 token 计价，而且输入和输出单价不同（输出通常更贵）。这会影响你的提示词写法 —— 让模型「少说废话」不只是为了好看，也是在省钱。

**延迟**：先记住三个指标的名字，第 12 章再正式做预算表。

| 指标       | 全称                    | 量度什么           |
| -------- | --------------------- | -------------- |
| **TTFT** | Time to First Token   | 从发出请求到第一个字出现   |
| **TPOT** | Time per Output Token | 每个输出 token 的耗时 |
| **E2E**  | End-to-End            | 从提问到答案说完的总时长   |

同一个问题，「先想后答」比「直接答」慢；prompt 越长，第一个字出现的就越晚（因为要先把整段 prompt「读」一遍）。

> **一次任务的等待时间，主要是一轮轮串行调用加起来。** 从第 3 章起，一轮里会出现 3 次、5 次、8 次调用，每一次都要等前一次回来。

## 2.3.4 换模型只改一个文件

市面上的模型有强有弱，有贵有便宜。你现在不必选定一家，但要知道两件事。

**第一，模型有梯度，任务也有轻重。** 

大模型更聪明也更贵，小模型更快也更便宜。很多简单任务（分类、抽取、格式转换）用小模型完全够用。把轻量的任务交给便宜的模型，是第 12 章「分级路由」要省的钱，这里先有这个意识就够了。


**第二，把「调模型」这件事包成一个函数。**

不同供应商的接口大同小异，你的代码不该被任何一家的细节绑死。做法很简单：写一个薄薄的 `llm.py`，把调用包起来。

```python
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
```

这件事看起来不起眼，却是 harness 架构的第一步：**从今往后，你的代码只跟 `chat()` 打交道，不直接碰 SDK。** 想换模型、想加一个备用供应商、想在调用时统一记日志和算成本——都只需要动这一个文件。

没有工具时不要把 `tools=None` 传进去，有的供应商会当成非法参数。2.1 节说过，DeepSeek 开着思考模式时 `temperature` 不生效，以供应商文档为准。

我们在第 1 章说过：换一台发动机，车还在，调用方式要做一层适配。`llm.py` 就是这层。第 14 章会看到 DeepSeek Harness 把适配器做成可以替换的。
