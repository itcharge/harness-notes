# 6.1 从对话历史到轨迹：会话日志是追加式事件流

## 6.1.1 一次任务里发生了什么

Harnex 现在能读文件、改文件了（第 4 章）。给它一件你几乎每天都干的小事：

> 把 src/uploader.py 里的重试次数从 0 改成 3，然后跑一下测试。

它来回几轮做完这件事。按时间顺序，发生了这些：

```text
T0  用户输入这句话
T1  模型请求调用 fs_read(path="src/uploader.py")
T2  工具返回文件内容（62 行）
T3  模型请求调用 apply_patch(path="src/uploader.py", old="retries = 0", new="retries = 3")
T4  工具返回错误：要替换的原文在 src/uploader.py 里出现 2 次，无法定位
T5  模型请求调用 apply_patch(同一个文件，old 里多带两行上下文)
T6  工具返回「已修改 src/uploader.py（3 行 → 3 行）」
T7  模型请求调用 shell(command="pytest -q")
T8  工具返回「5 passed in 0.4s」
T9  模型给出最终答复「重试次数已改成 3，5 个测试全过」
```

十件事。现在问一句：**这些事里，哪些在后面的对话里还会被用到？**

第 3 章的 `messages` 只留下了其中一部分：

- **留下的部分**：模型继续推理要用的那些——你这句话、模型的工具请求、工具返回、模型的回答。
- **没留下的部分**：第几秒发生的、属于哪一次会话、写文件时谁批的、第一次 `apply_patch` 为什么没改成、那次 `pytest` 跑了多久。

**没留下来的这部分，恰恰是事后最想要的。**

三天后你想知道「`retries` 是谁让改的、改之前是多少、第一次为什么没改成、测试跑了多久」——`messages` 一个都答不上来。它进程一退出就没了，而且它本来就不是为回答这类问题准备的。

## 6.1.2 发给模型的只是一份投影

有两个东西长得很像，作用完全不同，这里必须先分开。

**`messages`：这一轮要发给模型的东西。** 它只干一件事——让下一次模型调用读懂上下文。所以它可以被裁剪、被摘要、被重排，只要模型还读得懂就行。

**会话日志：这件事到底发生过什么。** 它只增不减，按时间排好，随时能回放。它服务的是你、是调试器、是三天后想追问细节的人。

打个比方：**`messages` 像会议桌上那份材料，边开边改；会话日志像会议录音，录完就不动。**

> 记住一句：**`messages` 是从日志里投影出来的，日志不能反过来从 `messages` 里拼。**

「投影」听着抽象，其实就是**不另存一份，要用时从日志现算一遍**。要发给模型的消息列表，就是把日志里该给模型看的那些事件挑出来、排成消息的样子。

## 6.1.3 事件一条条长什么样

会话日志的基本单位是**事件（event）**，不是消息。一次任务里会出现的事件，大致就这几类：

| 事件类型 | 发生时机 | 关键字段 |
| --- | --- | --- |
| `session_start` | 会话开始 | 时间、系统提示摘要、可用工具 |
| `user_message` | 用户输入 | 文本 |
| `assistant_message` | 模型返回 | 文本与/或工具请求 |
| `tool_result` | 工具执行完 | 结果文本、工具名、耗时 |
| `user_interrupt` | 用户打断或纠正 | 文本 |
| `compaction` | 发生了一次压缩 | 压缩摘要 |
| `error` | 出错了 | 错误类型与位置 |

每条事件都有两个相同的字段：**发生了什么**（`kind`）和**什么时候**（`ts`）。其余字段都是这一类事件自己的负载。

注意：消息在这里只是 **事件的一种**。`assistant_message` 里装着模型说的话，`tool_result` 里装着工具的输出——它们不再是日志的全部，只是其中两类条目。

**为什么不索性把日志做成消息列表？** 因为一次任务里值得记的东西，比「模型看过的话」多。用户中途打断、某次调用重试了三次、压缩发生过一次——这些都不是消息。少了它们，就答不出「它当时为什么会这么想」。

## 6.1.4 两条要守住的规则

日志要立得住，先钉两条规矩。它们叫 **不变式**——意思是程序跑到哪一步，它们都必须成立。

**不变式一：模型可见即已记录。**

凡是进到模型上下文里的内容，都必须能从日志重建。反过来也一样：**日志里没有的，就不该出现在模型眼前。**

这条听着严，用处却大：它让「模型到底看到过什么」变成一件 **可查** 的事。Harnex 说了句莫名其妙的话，第一反应不该是「模型抽什么风」，而是「它这一轮看到了什么」——日志能答。

**不变式二：状态由日志投影得出。**

Harnex 不另外存一份「当前状态」。它眼里的当前状态，是把日志投影一遍算出来的。要发给模型的消息列表，就是这么一次投影的结果。

为什么不索性存一份状态、改到哪跟到哪？三个理由：

- **不会漂移。** 存一份状态，每次变更都得同步改它，漏一次就永远对不上。日志只追加，没有「同步」这个动作，也就没有对不上的机会。
- **可回放。** 从头投影一遍，整个任务就重放了。查 bug 出在哪一步，这几乎是唯一靠谱的办法。
- **可换投影。** 同一份日志，能投影成给模型的消息，也能投影成人看的轨迹、统计用的指标——**记录只有一份，用途随意。**

后两条第 10 章（断点恢复）和第 12 章（可观测）会重点用，地基在这一节打好。

## 6.1.5 写成只追加的日志

先写日志本身：一个只追加的类，每条事件落成一行 JSON。

```python
# harnex/session/log.py —— 会话日志：只追加的事件流，落成 JSONL
import json
import time
from pathlib import Path

LOG_DIR = Path("sessions")


class SessionLog:
    """只追加、不修改的事件流。它同时是真相源和恢复点。"""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or time.strftime("%Y%m%d-%H%M%S")
        self.path = LOG_DIR / f"{self.session_id}.jsonl"
        self.path.parent.mkdir(exist_ok=True)
        self._events: list[dict] = []

    def append(self, kind: str, **payload) -> dict:
        """写一条事件：先落磁盘，再回内存。"""
        event = {"seq": len(self._events), "ts": round(time.time(), 3),
                 "kind": kind, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._events.append(event)
        return event

    def events(self) -> list[dict]:
        return list(self._events)

    @classmethod
    def load(cls, session_id: str) -> "SessionLog":
        """从磁盘恢复一个会话：把 JSONL 读回内存。"""
        log = cls(session_id)
        text = log.path.read_text(encoding="utf-8") if log.path.exists() else ""
        log._events = [json.loads(line) for line in text.splitlines() if line.strip()]
        return log


def project(events: list[dict]) -> list[dict]:
    """把事件流投影成「可以发给模型的消息列表」。"""
    messages = []
    for e in events:
        if e["kind"] == "user_message":
            messages.append({"role": "user", "content": e["content"]})
        elif e["kind"] == "assistant_message":
            messages.append(e["message"])
        elif e["kind"] == "tool_result":
            messages.append({"role": "tool",
                             "tool_call_id": e["tool_call_id"],
                             "content": e["content"]})
    return messages
```

三个地方值得留意一下：

- **`append()` 先落磁盘，再回内存。** 反过来的话，进程要是在两次写之间崩了，内存里那条就永远丢了——而它可能正是用户刚说的话。
- **用 JSONL（一行一个 JSON），不用一个大 JSON。** 追加就是写一行，不用重写整个文件；文件被截断，前面完好的行还能用。
- **`project()` 只认三种事件。** `session_start`、`compaction`、`error` 都不投影成消息——模型看不见，但**你**看得见。这就是「日志比消息多」的具体样子。

## 6.1.6 接到主循环

再把主循环接上它：

```python
# harnex/loop/agent.py 片段 —— Harnex v0.4：事件落进日志，消息由日志投影
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
```

`model_dump()` 那行不能省：`chat()` 返回的是 SDK 的消息对象，而事件要写进 JSON，得先转成普通字典。不做这一步，`json.dumps` 直接报错。

还有一处不在这个函数里，但在 `main()` 里：**`log` 只建一次，整个会话共用。** 照旧那个 `while True` 循环，只是循环外多一行 `log = SessionLog()`，循环里改调 `run_turn(q, registry, log, system)`。

这才是本章真正解决「跨轮记忆」的地方。每问一句，`run_turn()` 都把整份日志重新投影一遍，所以第二轮看得到第一轮说过的话——**前提是 `log` 是同一个。** 要是在 `run_turn()` 里新建一个 `SessionLog()`，那就又变回「每句话都是初次见面」了。

`sessions/20261011-191700.jsonl` 里会长出这样的内容：

```text
{"seq":0,"ts":1758021420.1,"kind":"user_message","content":"把 src/uploader.py 里的重试次数从 0 改成 3…"}
{"seq":1,"ts":1758021421.4,"kind":"assistant_message","message":{"role":"assistant","tool_calls":[…]}}
{"seq":2,"ts":1758021421.6,"kind":"tool_result","tool_call_id":"call_a1","name":"fs_read","content":"1  import time\n2  import json\n3  …"}
{"seq":3,"ts":1758021422.8,"kind":"assistant_message","message":{"role":"assistant","tool_calls":[…]}}
```

「它这一轮看到了什么」到这里有了确定的答案：**把 `seq` 按顺序读一遍，就是它当时的全部视野。**

到这一步，Harnex 有了记性。可记性一好，新问题立刻冒出来：**日志在长，能发给模型的窗口却是有限的。** 下一节算这笔账。
