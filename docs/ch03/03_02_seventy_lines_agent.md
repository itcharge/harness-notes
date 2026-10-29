# 3.2 七十行代码，一个完整的 Agent：从内核到 CLI

上一节问了五个问题，并说这一节会按「想、记、停、熔断、做、看」走完一圈。下面这份脚本就是那一圈。先通读一遍，再拿「上海现在天气怎么样」走一遍。

```python
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
```

这份脚本一共 75 行。其中真正构成「循环」的，只有 `run()` 里那十来行。其余代码是两个工具，以及一份告诉模型「可以调用什么」的清单。

这十来行里，让循环转起来的是标着 ①②③④ 的那几行：④ `for` 起圈、① `chat` 出决定、② `append` 记历史、③ `if not msg.tool_calls` 判停、`return` 交答案。上面这整份脚本就是 **Harnex v0.1**，落在 [`codes/ch03/harnex_v0.1/loop/agent.py`](../../codes/ch03/harnex_v0.1/loop/agent.py)。`chat()` 在同目录的 [`llm/client.py`](../../codes/ch03/harnex_v0.1/llm/client.py)。从第 4 章起，每一章的 `codes/chNN/harnex_v0.x/` 都是到该章为止能单独跑的一份，版本号每章加 0.1，到第 12 章为 `harnex_v1.0`。文件直接放在该目录下，不套 `src/harnex`。

`chat()` 来自第 2 章的 `llm.py`。本章不直接写模型厂商的调用代码：

```python
# harnex/llm/client.py —— 唯一直接接触模型 SDK 的地方（第 2 章产物，本章直接复用）
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

上面这几行和 [`codes/ch03/harnex_v0.1/llm/client.py`](../../codes/ch03/harnex_v0.1/llm/client.py) 里那一份逐字相同。文件开头还定死了三个值：`api_key` 从环境变量取，`base_url="https://api.deepseek.com"`，`_model = "deepseek-flash"`。换模型或换供应商，只改这三个值。

`if tools:` 这一行是 2.3.4 留下的规矩：本轮没有工具时，不要把 `tools=None` 传进去。所以这里的 `kwargs` 是现攒的，不是把 `tools=tools` 写死在调用里。

**怎么跑起来。** 先 `cd` 进这份代码的目录，再用 `-m` 从目录本身启动：

```bash
cd codes/ch03/harnex_v0.1
python -m loop.agent
```

不要写成 `python loop/agent.py`。那样启动，Python 只把脚本所在的 `loop/` 放进模块搜索路径，开头那句 `from llm import chat` 会报 `ModuleNotFoundError: No module named 'llm'`。用 `-m` 启动时，当前目录本身就在搜索路径上，`llm` 和 `loop` 都能找到，也不用设 `PYTHONPATH`。装好 `openai`、Key 放进环境变量以后，看到 `你> ` 就是在等输入了。

## 3.2.1 走一遍：查上海天气

`for _ in range(MAX_STEPS)` 那一行就是熔断，最多 8 圈。问一句「上海现在天气怎么样」，实际走了两圈：

```text
第 1 圈
  想    把这句话发给模型
        模型返回：请调用 get_weather，城市是上海
  记    把模型这条回复追加进 messages
  停？  它还要工具，不停
  做    执行 get_weather({"city": "上海"})，得到「上海：晴，26℃」
  看    把这句结果追加进 messages

第 2 圈
  想    模型看到「晴，26℃」，不再要工具，直接写出回答
  记    把这句回答追加进 messages
  停    没有 tool_calls，把回答交给你
```

看这三件事：

1. **模型被调用了两次。** 第一次只返回「请调用 `get_weather`」。第二次看到「上海：晴，26℃」，才写出给人看的回答。第二次要等第一次结束。
2. **真正执行工具的是你的代码。** 按名字从 `TOOLS` 取出函数，读出参数，再调用。模型返回的是名字和参数。
3. **`messages` 每圈都在变长。** 每转一圈，会将模型的回复和工具结果都追加到消息中。它能根据晴天作答，是因为结果写回了 `messages` 列表。这就是第 6 章「会话日志」的最初形态。

## 3.2.2 每一段在产品里叫什么

上一节的五个问题，就在这几行：

| 本章代码                    | 它是什么   | 真实 harness 里的名字                           |
| ----------------------- | ------ | ----------------------------------------- |
| `MAX_STEPS`             | 熔断上限   | Codex 的步数上限、LangGraph 的 `recursion_limit` |
| `messages`              | 状态载体   | 会话日志 / session log（第 6 章）                 |
| `TOOLS`                 | 执行器    | 工具注册表 ToolRegistry（第 4 章）                 |
| `if not msg.tool_calls` | 正常终止条件 | 循环停止判断                                    |
| （没有）                    | 权限策略   | 审批与沙箱（第 15 章），本章的空位                       |

这几行以后会变长，先把名字认准。`TOOLS` 到第 4 章做成工具注册表。`messages` 到第 6 章留下来，变成会话日志。圈数上限到第 10 章再加「等太久也停」。问不问人，分在第 4、11、15 章补上。

## 3.2.3 这几行是关键

上一节说过，如果没有圈数上限，一次提问就有可能无限反复用工具。落到代码实现时，下边要特别留意这三行，每行都少不了，否则程序会出错或行为异常。

- **圈数上限 `MAX_STEPS`。** 

没有它，模型可能陷入「反复调用同一个工具」的死循环 —— 查一次天气不满意，再查一次，再查一次。

- **工具结果必须写成字符串。** 

`content` 字段的要求是字符串。如果工具函数返回数字、列表、对象时，先用 `str(result)` 转成字符串再放进 `messages`。不转的话，调用会报错，或者模型读不懂这段结果。

- **先记下模型的调用，再记下工具的结果。** 

`assistant` 那条消息（含 `tool_calls`）**必须先于** 它的 `tool` 结果出现，`tool_call_id` 必须等于 `call.id`。

```text
对： user → assistant(含 tool_calls) → tool(结果) → assistant(最终回答)
错： user → tool(结果)                                  ← 结果没有来处，直接报错
错： user → assistant → tool(tool_call_id 写错)          ← 对不上号，直接报错
```

**动手体会一下**：把 `messages.append(msg)` 这一行注释掉再运行，程序就会报错：工具结果对不上一次调用。这一行是在告诉下一圈，上一步模型要的是这个工具。

## 3.2.4 做成命令行

上面的代码已经带了 CLI 外壳——一个 `while True`，读到 `exit` 或空行就退出：

```python
if __name__ == "__main__":
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", run(q))
```

跑起来是这样：

```text
你> 现在几点？
Harnex> 现在是 2026-10-09 23:41。
你> 上海天气怎么样？
Harnex> 上海今天晴，26℃，适合出行。
你> 现在几点，顺便说说上海天气
Harnex> 现在是 23:41；上海晴、26℃。
你> exit
```

每一句都会重新调用 `run()`。`run()` 开头是：

```python
messages = [{"role": "user", "content": user_input}]
```

这一次的 `messages` 里只有这句新问题。问完上海天气，再问「那北京呢」，它不知道「那」指的是天气，也不记得上一句是上海。

能接着输入下一句，还不等于记得住上一句。让 `messages` 留到下一句，并在太长时压成一段摘要，是第 6 章要做的事。

这一版还没做的，都留在后面：

| 现在没有 | 你会碰到 | 补在 |
| --- | --- | --- |
| 关掉程序之后记录还在 | 一关就没了 | 第 6 章 |
| 下一句记得上一句 | 「那北京呢」接不上 | 第 6 章 |
| 危险动作先问你 | 模型说做就做 | 第 4、11、15 章 |
| 失败了还能继续 | 一次出错就整个停住 | 第 10 章 |

这一章先让这个循环跑起来。后面每一章往这几行上加一件事。
